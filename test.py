from datasets import load_dataset
from synapses.gpt2 import GPT2LMSynapse, nextbatch
import bittensor

data = load_dataset('cnn_dailymail', '3.0.0')['train']

inputs = nextbatch(data, 1, bittensor.__tokenizer__())

print(inputs)