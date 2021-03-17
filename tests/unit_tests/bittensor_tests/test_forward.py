import bittensor
import torch
import pytest
from unittest.mock import MagicMock
from torch.autograd import Variable

bittensor.init()
bittensor.dendrite._dendrite.forward = MagicMock(return_value = [torch.tensor([]), [0], ['']]) 
bittensor.dendrite._dendrite.backward = MagicMock(return_value = [torch.tensor([]), [0], ['']]) 

neuron_pb2 = bittensor.proto.Neuron(
    version = bittensor.__version__,
    public_key = bittensor.neuron.wallet.hotkey.public_key,
    address = '0.0.0.0',
    port = 12345,
)

def test_dendrite_forward_tensor_shape_error():
    x = torch.rand(3, 3, 3)
    with pytest.raises(ValueError):
        bittensor.dendrite.forward_tensor( neurons=[neuron_pb2], inputs=[x])

def test_dendrite_forward_image_shape_error():
    x = torch.rand(3, 3, 3)
    with pytest.raises(ValueError):
        bittensor.dendrite.forward_image( neurons=[neuron_pb2], inputs=[x])

def test_dendrite_forward_text_shape_error():
    x = torch.rand(3, 3, 3)
    with pytest.raises(ValueError):
        bittensor.dendrite.forward_image( neurons=[neuron_pb2], inputs=[x])

def test_dendrite_forward_text():
    x = torch.tensor([[1,2,3,4],[5,6,7,8]], dtype=torch.long)
    bittensor.dendrite._dendrite.forward = MagicMock(return_value = [ [torch.zeros([2, 4, bittensor.__network_dim__])], [0], ['']]) 
    codes, tensors  = bittensor.dendrite.forward_text( neurons=[neuron_pb2], inputs=[x])
    assert codes[0].item() == bittensor.proto.ReturnCode.Success
    assert list(tensors[0].shape) == [2, 4, bittensor.__network_dim__]

def test_dendrite_forward_image():
    x = torch.tensor([ [ [ [ [ 1 ] ] ] ] ])
    bittensor.dendrite._dendrite.forward = MagicMock(return_value = [ [torch.zeros([1, 1, bittensor.__network_dim__])] , [0], ['']]) 
    codes, tensors  = bittensor.dendrite.forward_image( neurons=[neuron_pb2], inputs=[x])
    assert codes[0].item() == bittensor.proto.ReturnCode.Success
    assert list(tensors[0].shape) == [1, 1, bittensor.__network_dim__]

def test_dendrite_forward_tensor():
    x = torch.rand(3, 3, bittensor.__network_dim__)
    bittensor.dendrite._dendrite.forward = MagicMock(return_value = [ [torch.zeros([3, 3, bittensor.__network_dim__])], [0], ['']]) 
    codes, tensors = bittensor.dendrite.forward_tensor( neurons=[neuron_pb2], inputs=[x])
    assert codes[0].item() == bittensor.proto.ReturnCode.Success
    assert list(tensors[0].shape) == [3, 3, bittensor.__network_dim__]

def test_dendrite_forward_tensor_pass_through_text():
    x = torch.rand(3, 3)
    y = torch.zeros([3, 3, bittensor.__network_dim__])
    bittensor.dendrite._dendrite.forward = MagicMock(return_value = [ [y, y, y] , [0, 0, 0], ['','',''] ]) 
    codes, tensors = bittensor.dendrite.forward_text( neurons=[neuron_pb2, neuron_pb2, neuron_pb2], inputs=[x, x, x])
    assert codes[0].item() == bittensor.proto.ReturnCode.Success
    assert codes[1].item() == bittensor.proto.ReturnCode.Success
    assert codes[2].item() == bittensor.proto.ReturnCode.Success
    assert tensors[0].shape == y.shape
    assert tensors[1].shape == y.shape
    assert tensors[2].shape == y.shape

def test_dendrite_forward_tensor_pass_through_image():
    x = torch.rand(3, 3, 3, 3, 3)
    y = torch.zeros([3, 3, bittensor.__network_dim__])
    bittensor.dendrite._dendrite.forward = MagicMock(return_value = [ [y, y, y] , [0, 0, 0], ['','','']]) 
    codes, tensors = bittensor.dendrite.forward_image( neurons=[neuron_pb2, neuron_pb2, neuron_pb2], inputs=[x, x, x])
    assert codes[0].item() == bittensor.proto.ReturnCode.Success
    assert codes[1].item() == bittensor.proto.ReturnCode.Success
    assert codes[2].item() == bittensor.proto.ReturnCode.Success
    assert tensors[0].shape == y.shape
    assert tensors[1].shape == y.shape
    assert tensors[2].shape == y.shape

def test_dendrite_forward_tensor_pass_through_tensor():
    x = torch.rand(3, 3, bittensor.__network_dim__)
    y = torch.zeros([3, 3, bittensor.__network_dim__])
    bittensor.dendrite._dendrite.forward = MagicMock(return_value = [ [y, y, y] , [0, 0, 0], ['','','']]) 
    codes, tensors = bittensor.dendrite.forward_tensor( neurons=[neuron_pb2, neuron_pb2, neuron_pb2], inputs=[x, x, x])
    assert codes[0].item() == bittensor.proto.ReturnCode.Success
    assert codes[1].item() == bittensor.proto.ReturnCode.Success
    assert codes[2].item() == bittensor.proto.ReturnCode.Success
    assert tensors[0].shape == y.shape
    assert tensors[1].shape == y.shape
    assert tensors[2].shape == y.shape

def test_dendrite_backward():
    x = Variable(torch.ones(1, 1), requires_grad=True)
    y = torch.ones(1, 1)
    bittensor.dendrite._dendrite.forward = MagicMock(return_value = [ [y], [0], ['']]) 
    bittensor.dendrite._dendrite.backward = MagicMock(return_value = [ [y], [0], ['']]) 
    codes, tensors = bittensor.dendrite.forward_text( neurons=[ neuron_pb2 ], inputs=[ x ])
    tensors[0].backward()
    assert x.grad.item() == 1

def test_dendrite_backward_large():
    x = Variable(torch.ones(1, 2), requires_grad=True)
    y = torch.ones(1, 2)
    bittensor.dendrite._dendrite.forward = MagicMock(return_value = [ [y], [0], ['']]) 
    bittensor.dendrite._dendrite.backward = MagicMock(return_value = [ [y], [0], ['']]) 
    codes, tensors = bittensor.dendrite.forward_text( neurons=[ neuron_pb2 ], inputs=[ x ])
    tensors[0].sum().backward()
    assert list(x.grad.shape) == [1, 2]
    assert x.grad.tolist() == y.tolist()

def test_dendrite_backward_multiple():
    x1 = Variable(torch.rand(1, 1), requires_grad=True)
    x2 = Variable(torch.rand(1, 1), requires_grad=True)
    x3 = Variable(torch.rand(1, 1), requires_grad=True)
    y1 = torch.ones(1, 1)
    y2 = torch.ones(1, 1)
    y3 = torch.ones(1, 1)

    bittensor.dendrite._dendrite.forward = MagicMock(return_value = [ [y1, y2, y3], [0,0,0], ['','','']]) 
    bittensor.dendrite._dendrite.backward = MagicMock(return_value = [ [y1, y2, y3], [0,0,0], ['','','']]) 
    codes, tensors = bittensor.dendrite.forward_text( neurons=[ neuron_pb2, neuron_pb2, neuron_pb2 ], inputs=[ x1, x2, x3 ])
    tensors[0].backward()
    assert list(x1.grad.shape) == [1, 1]
    assert x1.grad.tolist() == y1.tolist()
    x2.grad.data.zero_()
    assert x2.grad.tolist() == [[0]] 
    tensors[1].backward()
    assert list(x2.grad.shape) == [1, 1]
    assert x2.grad.tolist() == y2.tolist()
    x3.grad.data.zero_()
    assert x3.grad.tolist() == [[0]] 
    tensors[2].backward()
    assert list(x3.grad.shape) == [1, 1]
    assert x3.grad.tolist() == y3.tolist()


if __name__  == "__main__":
    test_dendrite_backward_multiple()
