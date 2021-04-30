"""GPT Synapse
    - Initial stem consists of a combination of token encodings and positional encoding. 
    - Basically, a uniform sequence of Transformer blocks.
        - Each transformer is a sequential combination of a 1-hidden layer MLP block and a self-attention block.
        - all blocks feed into a central residual pathway similar to resnets.
    - Final decoder is a linear projection into a vanilla softmax. 
    - This implementation is based on Karpathy et al.'s implementation of minGPT.
"""

import argparse
import math
import bittensor
import torch
import torch.nn as nn
from munch import Munch


from torch.nn import functional as F
from routers.pkm import PKMRouter
from types import SimpleNamespace

class GPTPooler(nn.Module):

    def __init__(self, config):
        super().__init__()
        self.dense = nn.Linear(config.n_embd, config.n_embd)
        self.activation = nn.Tanh()

    def forward(self, hidden_states):
        # We "pool" the model by simply taking the hidden state corresponding
        # to the first token.
        first_token_tensor = hidden_states[:, 0]
        pooled_output = self.dense(first_token_tensor)
        pooled_output = self.activation(pooled_output)
        return pooled_output

class GPTConfig:
    """Base GPT config, params common to all GPT versions.
    """
    embd_pdrop = 0.1
    resid_pdrop = 0.1
    attn_pdrop = 0.1

    def __init__(self, vocab_size: int, block_size: int, **kwargs):
        """GPTConfig constructor

        Args:
            vocab_size (:int:): Size of the vocabulary
            block_size (:int:): How many transformer blocks
        """
        self.vocab_size = vocab_size
        self.block_size = block_size
        for k, v in kwargs.items():
            setattr(self, k, v)

class Block(nn.Module):
    """
    Transformer block!
    """

    def __init__ (self, config):
        """Constructor

        Args:
            config (`GPTConfig`): Configuration containing n_embd and n_head
        """
        super().__init__()
        
        assert hasattr(config, 'n_embd')
        assert hasattr(config, 'n_head')

        self.ln1 = nn.LayerNorm(config.n_embd)
        self.ln2 = nn.LayerNorm(config.n_embd)
        self.attn = CausalSelfAttention(config)
        self.mlp = nn.Sequential(
            nn.Linear(config.n_embd, 4 * config.n_embd),
            nn.GELU(),
            nn.Linear(4 * config.n_embd, config.n_embd),
            nn.Dropout(config.resid_pdrop)
        )

    def forward(self, x):
        x = x + self.attn(self.ln1(x))
        x = x + self.mlp(self.ln2(x))
        return x


class CausalSelfAttention(nn.Module):
    """
    A vanilla multi-head masked self-attention layer with a projection at the end.

    TODO (shibshib): Investigate using torch.nn.MultiheadAttention here.
    """

    def __init__(self, config):
        super().__init__()
        assert config.n_embd % config.n_head == 0
        # key, query, value projections for all heads
        self.key = nn.Linear(config.n_embd, config.n_embd)
        self.query = nn.Linear(config.n_embd, config.n_embd)
        self.value = nn.Linear(config.n_embd, config.n_embd)
        # regularization
        self.attn_drop = nn.Dropout(config.attn_pdrop)
        self.resid_drop = nn.Dropout(config.resid_pdrop)
        # output projection
        self.proj = nn.Linear(config.n_embd, config.n_embd)
        # causal mask to ensure that attention is only applied to the left in the input sequence
        self.register_buffer("mask", torch.tril(torch.ones(config.block_size, config.block_size))
                                     .view(1, 1, config.block_size, config.block_size))
        self.n_head = config.n_head

    def forward(self, x, layer_past=None):
        B, T, C = x.size()

        # calculate query, key, values for all heads in batch and move head forward to be the batch dim
        k = self.key(x).view(B, T, self.n_head, C // self.n_head).transpose(1, 2) # (B, nh, T, hs)
        q = self.query(x).view(B, T, self.n_head, C // self.n_head).transpose(1, 2) # (B, nh, T, hs)
        v = self.value(x).view(B, T, self.n_head, C // self.n_head).transpose(1, 2) # (B, nh, T, hs)

        # causal self-attention; Self-attend: (B, nh, T, hs) x (B, nh, hs, T) -> (B, nh, T, T)
        att = (q @ k.transpose(-2, -1)) * (1.0 / math.sqrt(k.size(-1)))
        att = att.masked_fill(self.mask[:,:,:T,:T] == 0, float('-inf'))
        att = F.softmax(att, dim=-1)
        att = self.attn_drop(att)
        y = att @ v # (B, nh, T, T) x (B, nh, T, hs) -> (B, nh, T, hs)
        y = y.transpose(1, 2).contiguous().view(B, T, C) # re-assemble all head outputs side by side

        # output projection
        y = self.resid_drop(self.proj(y))
        return y

class GPT2Synapse(bittensor.synapse.Synapse):

    def __init__(self, config, **kwargs):
        super(GPT2Synapse, self).__init__(config = config, **kwargs)
        """The full GPT language model, with context of a block size.
            Args:
                config (:obj: `munch.Munch`, `required`):
                    munched config class.
        """

        if config == None:
            config = GPT2Synapse.default_config()
        
        bittensor.config.Config.update_with_kwargs(config.synapse, kwargs)
        GPT2Synapse.check_config(config)
        self.config = config

        gpt_config = GPTConfig(
            vocab_size = bittensor.__vocab_size__,
            n_embd=bittensor.__network_dim__,
            n_head=config.synapse.n_head,
            n_layer=config.synapse.n_layer,
            block_size=config.synapse.block_size,
            embd_pdrop=config.synapse.embd_pdrop,
            resid_pdrop=config.synapse.resid_pdrop,
            attn_pdrop=config.synapse.attn_pdrop
        )
        # Token embedding layer. 
        # [bittensor.__vocab_size__, bittensor.__network_dim__]
        self.tok_emb = nn.Embedding(gpt_config.vocab_size, gpt_config.n_embd)

        # Positional embedding.
        # [1, block_size, bittensor.__network_dim__]
        self.pos_emb = nn.Parameter(torch.zeros(1, gpt_config.block_size, gpt_config.n_embd))
        self.drop = nn.Dropout(gpt_config.embd_pdrop)

        # Transformer blocks
        self.blocks = nn.Sequential(*[Block(gpt_config) for _ in range(gpt_config.n_layer)])

        # Decoder head
        self.ln_f = nn.LayerNorm(gpt_config.n_embd)

        # Head
        # [ bittensor.__network_dim__, bittensor.__network_dim__ ]
        self.head = nn.Linear(gpt_config.n_embd, bittensor.__network_dim__, bias=False)

        # pooler_layer: pools the hidden units for use by the pkm dendrite rpc query.
        self.pooler = GPTPooler(gpt_config)

        # Router: (PKM layer) queries network using pooled embeddings as context.
        self.router = PKMRouter(config, query_dim = bittensor.__network_dim__)

        # Hidden layer
        self.hidden_layer = nn.Linear( bittensor.__network_dim__, bittensor.__network_dim__ )

        # Target layer
        self.target_layer = nn.Linear( bittensor.__network_dim__, gpt_config.vocab_size, bias=False )

        # Block size here corresponds to sequence lengths
        self.block_size = gpt_config.block_size
        self.apply(self._init_weights)

        # Loss function: MLM cross-entropy loss.
        # predicted: [batch_size, sequence_len, 1], targets: [batch_size, sequence_len, 1] -> [1]
        self.loss_fct = nn.CrossEntropyLoss()
                
        self.num_parameters = sum(p.numel() for p in self.parameters())
        self.to(self.device)
    
    @staticmethod   
    def default_config() -> Munch:
        parser = argparse.ArgumentParser(); 
        GPT2Synapse.add_args(parser) 
        config = bittensor.config.Config.to_config(parser); 
        return config

    @staticmethod
    def add_args(parser: argparse.ArgumentParser):
        """ Add model params
        """
        parser.add_argument('--synapse.n_head', default=32, type=int, 
                                help='Number of attention heads for each attention layer in the Transformer encoder.')
        
        parser.add_argument('--synapse.n_layer', default=12, type=int, 
                                help='Number of hidden layers in the Transformer encoder.')
        
        parser.add_argument('--synapse.block_size', default=20, type=int, 
                                help='Number of hidden layers in the Transformer encoder.')
        
        parser.add_argument('--synapse.embd_pdrop', default=0.1, type=float, 
                            help='GPT embedding dropout probability.')

        parser.add_argument('--synapse.resid_pdrop', default=0.1, type=float, 
                            help='GPT residual dropout probability.')
        
        parser.add_argument('--synapse.attn_pdrop', default=0.1, type=float, 
                            help='GPT attention dropout probability.')
        
        PKMRouter.add_args(parser)

    @staticmethod
    def check_config(config: Munch):
        pass

    def get_block_size(self):
        return self.block_size

    def _init_weights(self, module):
        if isinstance(module, (nn.Linear, nn.Embedding)):
            module.weight.data.normal_(mean=0.0, std=0.02)

            if isinstance(module, nn.Linear) and module.bias is not None:
                module.bias.data.zero_()
            
        elif isinstance(module, nn.LayerNorm):
            module.bias.data.zero_()
            module.weight.data.fill_(1.0)
    

    def forward_text(self, inputs: torch.LongTensor):
        """ Local forward inputs through the CLM GPT Synapse.

            Args:
                inputs (:obj:`torch.LongTensor` of shape :obj:`(batch_size, sequence_len)`, `required`): 
                    Batch_size length list of tokenized sentences.
            
            Returns:
                hidden (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, sequence_len, bittensor.__network_dim__)`, `required`): 
                    Hidden layer representation produced using the local_context.
        """
        # Truncate seq length of incoming inputs if they are too long
        initial_length = inputs.size(1)
        inputs = inputs if initial_length <= self.block_size else inputs[:, -self.block_size:]
        hidden = self.local_forward(inputs=inputs.to(self.device), training = False).local_hidden
        
        # Now pad the output tensor back to the original length
        if initial_length > self.block_size:
            diff = initial_length - self.block_size
            padding = (0,0,diff,0)
            hidden = torch.nn.functional.pad(hidden, padding, "constant", 0)
            
        return hidden


    def local_forward(self, inputs: torch.LongTensor, training : bool = True) -> SimpleNamespace:
        """ Forward pass through GPT2 synapse.

            Args:
                inputs (:obj:`torch.LongTensor` of shape :obj:`(batch_size, block_size)`, `required`): 
                    Batch_size length x list of text sentences.

                training (:obj:`bool')`, `optional`, defaults to True):
                    Switch to True if this forward pass computes a CLM loss.

            SimpleNamespace {
                    local_context (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, sequence_len, bittensor.__network_dim__)`, `required`):
                        Hidden layer context.

                    local_hidden (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, sequence_len, bittensor.__network_dim__)`, `required`):
                        Hidden layer encoding produced using local_context.

                    local_target (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, sequence_len, bittensor.__vocab_size__)`, `optional`):
                        GPT MLM Target predictions produced using local_context. 

                    local_target_loss (:obj:`torch.FloatTensor` of shape :obj:`(1)`, `optional`): 
                        GPT MLM loss using local_context.
                }
        """
        _, t = inputs.size()
        assert t <= self.block_size, "Cannot forward, model block size is exhausted."

        # FWD locally
        # Each index maps to a learnable vector
        token_embeddings = self.tok_emb(inputs) 
        # Each Position maps to a learnable vector
        position_embeddings = self.pos_emb[:, :t, :]

        output = SimpleNamespace()
        # Dropout on token embeddings and position embeddings
        out = self.drop(token_embeddings + position_embeddings)

        # 
        out = self.blocks(out)
        out = self.ln_f(out)
        output.local_context = self.head(out)

        output.local_hidden = self.hidden_layer(output.local_context)

        if training :
            output.local_target = self.target_layer(output.local_hidden)
            
            shift_logits = output.local_target[..., :-1, :].contiguous()
            shift_labels = inputs[..., 1:].contiguous()
            
            output.local_target_loss = self.loss_fct( shift_logits.view(-1, shift_logits.size(-1)), shift_labels.view(-1) )
            
                   
        return output


    def remote_forward(self, neuron: bittensor.neuron.Neuron, inputs: torch.LongTensor, training: bool) -> SimpleNamespace:
        """ Forward pass inputs and labels through the GPT2 module and into the remote network.


        Args:
            neuron (:obj: `bittensor.neuron.Neuron`, `required`):
                    Bittensor neuron, used for making queries to the remote network.

            inputs (:obj:`torch.LongTensor` of shape :obj:`(batch_size, sequence_len)`, `required`): 
                    Batch_size length list of text sentences.

            training (:obj:`bool')`, `optional`, defaults to True):
                Switch to True if this forward pass computes an MLM loss.

        Returns:
            self.local_forward() + SimpleNamespace ( 

                    remote_hidden (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, sequence_len, bittensor.__network_dim__)`, `optional`): 
                        Hidden layer encoding produced using the remote_context.

                    remote_target (:obj:`torch.FloatTensor` of shape :obj:`(batch_size,  bittensor.__vocab_size__)`, `optional`):
                        GPT MLM Target predictions using the remote_context.

                    remote_target_loss (:obj:`torch.FloatTensor` of shape :obj:`(1)`, `optional`):
                        GPT MLM loss using the remote_context.

                    distillation_loss (:obj:`torch.FloatTensor` of shape :obj:`(1)`, `optional`): 
                        Distillation loss between local_context and remote_context.

                    router (:obj:`SimpleNamespace`, `required`): 
                        Outputs from the pkm dendrite.
            )
        """
        inputs = torch.clamp(inputs, 0, bittensor.__vocab_size__) # Filter out of range tokens.
        # Run local model
        # output = SimpleNamespace
        output = self.local_forward(inputs, training)
        
        # pooled: pooled hidden layer from local run, used as query context
        pooled = self.pooler(output.local_hidden.detach())

        # remote_context: joined responses from a dendrite.forward_text call.
        # remote_context.shape = [batch_size, sequence_len (or block_size), bittensor.__network_dim__]
        output.router = self.router.forward_text(neuron, inputs.to(self.device), pooled)
        remote_context = output.router.response.to(self.device)
        
        # distillation_loss : distillation loss between local_context and remote_context
        # distillation_loss.shape = [1]
        output.distillation_loss = F.mse_loss(output.local_context, remote_context.detach())

        # remote_hidden: hidden l;ayer encoding using remote_context.
        # remote_hidden.shape = [batch_size, sequence_len, bittensor.__network_dim__]
        output.remote_hidden = self.hidden_layer(remote_context)

        if training:
            # remote_target : projection of remote_hidden onto the target dimension
            # remote_target.shape = [batch_size, sequence_len, bittensor.__vocab_size__]
            output.remote_target = self.target_layer(output.remote_hidden)

            # remote_target_loss : CLM loss between remote_target and passed_targets.
            # remote_target_loss.shape = [1]
            shift_logits = output.remote_target[..., :-1, :].contiguous()
            shift_labels = inputs[..., 1:].contiguous()


            output.remote_target_loss = self.loss_fct(shift_logits.view(-1, shift_logits.size(-1)), shift_labels.view(-1))
            shift_labels.view(-1)
        
        return output

