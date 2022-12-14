# -*- coding: utf-8 -*-
"""pose estimation_objectron_dataset.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1PI12D8aGAJMGWYrcV4O1S8UauqPXJRIv

Resources - https://github.com/happyjin/ConvGRU-pytorch/blob/master/convGRU.py

Deep_layer_aggregation - https://arxiv.org/pdf/1707.06484.pdf

https://sites.google.com/view/centerpose

objectron - https://google.github.io/mediapipe/solutions/objectron.html#resources

pnp - https://docs.opencv.org/4.x/d5/d1f/calib3d_solvePnP.html

GRU - https://pytorch.org/docs/stable/generated/torch.nn.GRU.html#torch.nn.GRU

L1_loss - https://pytorch.org/docs/stable/generated/torch.nn.functional.l1_loss.html#torch.nn.functional.l1_loss

Focal_loss - https://pytorch.org/vision/0.12/_modules/torchvision/ops/focal_loss.html
"""

import numpy as np
import os
from matplotlib import pylab as plt

from skimage.transform import resize
from skimage import color

from tqdm import tqdm
import pickle
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import torchvision
import torchvision.transforms.functional as fn
import math
import joblib
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

class CentDla(nn.Module):
    def __init__(self,batch_size,num_Input_channels):
      super().__init__()
      
      self.c1_0 = nn.Conv2d(num_Input_channels,16,1,stride = 1)
      self.c1_1 = nn.Conv2d(16,16,5,stride = 2, padding= 2)
      #self.p1_1 = nn.MaxPool2d(2)
      self.c1_2 = nn.Conv2d(16,16,5,stride = 2, padding= 2)
      #stage1
      self.s1_c1 = nn.Conv2d(16,16,1,stride = 1)
      self.s1_c2 = nn.Conv2d(16,16,1,stride = 1)
      
      self.normalize_1 = nn.BatchNorm2d(16)
      #stage2
      self.s2_c1 = nn.Conv2d(16,32,5,stride = 2, padding= 2)
      self.s2_c2 = nn.Conv2d(32,32,1,stride = 1)
      #self.aggregate_2 = nn.Conv2d(64,64,1,stride=1)
      self.normalize_2 = nn.BatchNorm2d(32)
      self.s2_c3 = nn.Conv2d(32,32,1,stride = 1)
      self.s2_c4 = nn.Conv2d(32,32,1,stride = 1)
      
      self.aggregate_3 = nn.Conv2d(16,32,5,stride=2, padding =2)
      self.normalize_3 = nn.BatchNorm2d(32)
      self.u1 = nn.ConvTranspose2d(32,64,2, stride = 2, dilation = 1)
    def forward(self, x):
        x = F.rrelu(self.c1_0(x))                           #[16, 512, 512]
        #x = self.p1_1(x)
        x = F.rrelu(self.c1_1(x))                           #[16, 256, 256]
        x = F.rrelu(self.c1_2(x))                           #[16, 256, 256]

        #stage1
        x = F.rrelu(self.s1_c1(x))                          #[16, 128, 128]
        aggregate_layer_1 = x                               #[16, 128, 128]
        x = F.rrelu(self.s1_c2(x))                          #[16, 128, 128]
        #x = torch.squeeze(F.rrelu(self.normalize_1(torch.unsqueeze(self.aggregate_1(torch.cat((aggregate_layer_1,x),0)),0))))    #[32, 128, 128]
        x = torch.squeeze( F.rrelu( self.normalize_1(aggregate_layer_1+x) ) )    #[32, 128, 128]
        ida_1 = x
        #stage2
        x = F.rrelu(self.s2_c1(x))                          #[32, 64, 64]
        x = F.rrelu(self.s2_c2(x))                          #[32, 64, 64]
        aggregate_layer_2 = x  
        x = torch.squeeze(F.rrelu(self.normalize_2((aggregate_layer_2+x))))    #[32, 64, 64]
        aggregate_layer_2 = x 
        x = F.rrelu(self.s2_c3(x))    #[32, 64, 64]
        temp1=x                        
        x = F.rrelu(self.s2_c4(x))      #[32, 64, 64]
        x = aggregate_layer_2+temp1+x   
        x = F.rrelu(torch.squeeze( self.normalize_3(self.aggregate_3(ida_1) ) + x))   #[32, 64, 64] 
        x = self.u1(x)              
        return x


# dummy = torch.rand(8,3,512,512)
# model = CentDla(8,3)
# out1 = model(dummy)
# print(out1.shape)
# X = dummy
# Y = torch.rand(1,128,128)

import os
import torch
from torch import nn
from torch.autograd import Variable


class ConvGRUCell(nn.Module):
    def __init__(self, input_size, input_dim, hidden_dim, kernel_size, bias, dtype):
        """
        Initialize the ConvLSTM cell
        :param input_size: (int, int)
            Height and width of input tensor as (height, width).
        :param input_dim: int
            Number of channels of input tensor.
        :param hidden_dim: int
            Number of channels of hidden state.
        :param kernel_size: (int, int)
            Size of the convolutional kernel.
        :param bias: bool
            Whether or not to add the bias.
        :param dtype: torch.cuda.FloatTensor or torch.FloatTensor
            Whether or not to use cuda.
        """
        super(ConvGRUCell, self).__init__()
        self.height, self.width = input_size
        self.padding = kernel_size[0] // 2, kernel_size[1] // 2
        self.hidden_dim = hidden_dim
        self.bias = bias
        self.dtype = dtype

        self.conv_gates = nn.Conv2d(in_channels=input_dim + hidden_dim,
                                    out_channels=2*self.hidden_dim,  # for update_gate,reset_gate respectively
                                    kernel_size=kernel_size,
                                    padding=self.padding,
                                    bias=self.bias)

        self.conv_can = nn.Conv2d(in_channels=input_dim+hidden_dim,
                              out_channels=self.hidden_dim, # for candidate neural memory
                              kernel_size=kernel_size,
                              padding=self.padding,
                              bias=self.bias)

    def init_hidden(self, batch_size):
        return (Variable(torch.zeros(batch_size, self.hidden_dim, self.height, self.width)).type(self.dtype))

    def forward(self, input_tensor, h_cur):
        """
        :param self:
        :param input_tensor: (b, c, h, w)
            input is actually the target_model
        :param h_cur: (b, c_hidden, h, w)
            current hidden and cell states respectively
        :return: h_next,
            next hidden state
        """
        combined = torch.cat([input_tensor, h_cur], dim=1)
        combined_conv = self.conv_gates(combined)

        gamma, beta = torch.split(combined_conv, self.hidden_dim, dim=1)
        reset_gate = torch.sigmoid(gamma)
        update_gate = torch.sigmoid(beta)

        combined = torch.cat([input_tensor, reset_gate*h_cur], dim=1)
        cc_cnm = self.conv_can(combined)
        cnm = torch.tanh(cc_cnm)

        h_next = (1 - update_gate) * h_cur + update_gate * cnm
        return h_next


class ConvGRU(nn.Module):
    def __init__(self, input_size, input_dim, hidden_dim, kernel_size, num_layers,
                 dtype, batch_first=False, bias=True, return_all_layers=False):
        """
        :param input_size: (int, int)
            Height and width of input tensor as (height, width).
        :param input_dim: int e.g. 256
            Number of channels of input tensor.
        :param hidden_dim: int e.g. 1024
            Number of channels of hidden state.
        :param kernel_size: (int, int)
            Size of the convolutional kernel.
        :param num_layers: int
            Number of ConvLSTM layers
        :param dtype: torch.cuda.FloatTensor or torch.FloatTensor
            Whether or not to use cuda.
        :param alexnet_path: str
            pretrained alexnet parameters
        :param batch_first: bool
            if the first position of array is batch or not
        :param bias: bool
            Whether or not to add the bias.
        :param return_all_layers: bool
            if return hidden and cell states for all layers
        """
        super(ConvGRU, self).__init__()

        # Make sure that both `kernel_size` and `hidden_dim` are lists having len == num_layers
        kernel_size = self._extend_for_multilayer(kernel_size, num_layers)
        hidden_dim  = self._extend_for_multilayer(hidden_dim, num_layers)
        if not len(kernel_size) == len(hidden_dim) == num_layers:
            raise ValueError('Inconsistent list length.')

        self.height, self.width = input_size
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.kernel_size = kernel_size
        self.dtype = dtype
        self.num_layers = num_layers
        self.batch_first = batch_first
        self.bias = bias
        self.return_all_layers = return_all_layers

        cell_list = []
        for i in range(0, self.num_layers):
            cur_input_dim = input_dim if i == 0 else hidden_dim[i - 1]
            cell_list.append(ConvGRUCell(input_size=(self.height, self.width),
                                         input_dim=cur_input_dim,
                                         hidden_dim=self.hidden_dim[i],
                                         kernel_size=self.kernel_size[i],
                                         bias=self.bias,
                                         dtype=self.dtype))

        # convert python list to pytorch module
        self.cell_list = nn.ModuleList(cell_list)

    def forward(self, input_tensor, hidden_state=None):
        """
        :param input_tensor: (b, t, c, h, w) or (t,b,c,h,w) depends on if batch first or not
            extracted features from alexnet
        :param hidden_state:
        :return: layer_output_list, last_state_list
        """
        if not self.batch_first:
            # (t, b, c, h, w) -> (b, t, c, h, w)
            input_tensor = input_tensor.permute(1, 0, 2, 3, 4)

        # Implement stateful ConvLSTM
        if hidden_state is not None:
            raise NotImplementedError()
        else:
            hidden_state = self._init_hidden(batch_size=input_tensor.size(0))

        layer_output_list = []
        last_state_list   = []

        seq_len = input_tensor.size(1)
        cur_layer_input = input_tensor

        for layer_idx in range(self.num_layers):
            h = hidden_state[layer_idx]
            output_inner = []
            for t in range(seq_len):
                # input current hidden and cell state then compute the next hidden and cell state through ConvLSTMCell forward function
                h = self.cell_list[layer_idx](input_tensor=cur_layer_input[:, t, :, :, :], # (b,t,c,h,w)
                                              h_cur=h)
                output_inner.append(h)

            layer_output = torch.stack(output_inner, dim=1)
            cur_layer_input = layer_output

            layer_output_list.append(layer_output)
            last_state_list.append([h])

        if not self.return_all_layers:
            layer_output_list = layer_output_list[-1:]
            last_state_list   = last_state_list[-1:]

        return layer_output_list, last_state_list

    def _init_hidden(self, batch_size):
        init_states = []
        for i in range(self.num_layers):
            init_states.append(self.cell_list[i].init_hidden(batch_size))
        return init_states

    @staticmethod
    def _check_kernel_size_consistency(kernel_size):
        if not (isinstance(kernel_size, tuple) or
                    (isinstance(kernel_size, list) and all([isinstance(elem, tuple) for elem in kernel_size]))):
            raise ValueError('`kernel_size` must be tuple or list of tuples')

    @staticmethod
    def _extend_for_multilayer(param, num_layers):
        if not isinstance(param, list):
            param = [param] * num_layers
        return param

#creating neural network


class Pose_estimation_network(nn.Module):
    def __init__(self, batch_size,input_ch):
      super().__init__()
      self.rescale = torchvision.transforms.Resize((512,512))
      self.DLA = CentDla(batch_size,input_ch)
      use_gpu = torch.cuda.is_available()
      if use_gpu:
        dtype = torch.cuda.FloatTensor # computation in GPU
      else:
        dtype = torch.FloatTensor
      self.GRU_1 = ConvGRU(input_size=(128,128),input_dim=64,hidden_dim=[64,64],kernel_size=(3,3),num_layers=2,dtype=dtype,batch_first=True,bias = True,return_all_layers = False)
      self.GRU_2 = ConvGRU(input_size=(128,128),input_dim=64,hidden_dim=[64,64],kernel_size=(3,3),num_layers=2,dtype=dtype,batch_first=True,bias = True,return_all_layers = False)
      self.GRU_3 = ConvGRU(input_size=(128,128),input_dim=64,hidden_dim=[64,64],kernel_size=(3,3),num_layers=2,dtype=dtype,batch_first=True,bias = True,return_all_layers = False)
      
      self.Conv_branch_1 = nn.Conv2d(64,256,3,stride = 1,padding =1)
      self.Conv_branch_2 = nn.Conv2d(64,256,3,stride = 1,padding =1)
      self.Conv_branch_3 = nn.Conv2d(64,256,3,stride = 1,padding =1)

      self.Conv_Object_detection_branch_1 = nn.Conv2d(256,1,1,stride = 1)
      self.Conv_Object_detection_branch_2 = nn.Conv2d(256,2,1,stride = 1)
      self.Conv_Object_detection_branch_3 = nn.Conv2d(256,2,1,stride = 1)
      self.Conv_Keypoint_detection_branch_1 = nn.Conv2d(256,8,1,stride = 1)
      self.Conv_Keypoint_detection_branch_2 = nn.Conv2d(256,16,1,stride = 1)
      self.Conv_Keypoint_detection_branch_3 = nn.Conv2d(256,16,1,stride = 1)
      self.Conv_Cuboid_dimensions_branch = nn.Conv2d(256,3,1,stride = 1)
      
      

    def forward(self,x):
      x = self.rescale(x)
      x = self.DLA(x)
      Inp = torch.unsqueeze(x,0)
      x = self.GRU_1( Inp )
      branch_1 = x[0][0][0]
      x = self.GRU_2(x[0][0])
      branch_2 = x[0][0][0]
      x = self.GRU_3(x[0][0])
      branch_3 = x[0][0][0]

      branch_1 = self.Conv_branch_1(branch_1)
      branch_2 = self.Conv_branch_1(branch_2)
      branch_3 = self.Conv_branch_1(branch_3)

      object_center_heatmap = self.Conv_Object_detection_branch_1(branch_1)
      subpixel_offset = self.Conv_Object_detection_branch_2(branch_1)
      Bounding_box_sizes = self.Conv_Object_detection_branch_3(branch_1)

      keypoint_heatmaps =  self.Conv_Keypoint_detection_branch_1(branch_2)
      sub_pixel_offsets = self.Conv_Keypoint_detection_branch_2(branch_2)
      keypoint_displacements = self.Conv_Keypoint_detection_branch_3(branch_2)

      relative_cuboid_dimensions = self.Conv_Cuboid_dimensions_branch(branch_3)
      
      return object_center_heatmap,subpixel_offset,Bounding_box_sizes,keypoint_heatmaps,sub_pixel_offsets,keypoint_displacements,relative_cuboid_dimensions
      
# dummy = torch.rand(8,3,712,680)
# model = Pose_estimation_network(8,3)
# out1,out2,out3,out4,out5,out6,out7 = model(dummy)
# #out1 = model(dummy)
# print(out1.shape)
# X = dummy
# Y = torch.rand(1,128,128)

import torch
import torch.nn.functional as F

#from ..utils import _log_api_usage_once


def sigmoid_focal_loss(
    inputs: torch.Tensor,
    targets: torch.Tensor,
    alpha: float = 2,
    gamma: float = 4,
    reduction: str = "mean",
):
    """
    Original implementation from https://github.com/facebookresearch/fvcore/blob/master/fvcore/nn/focal_loss.py .
    Loss used in RetinaNet for dense detection: https://arxiv.org/abs/1708.02002.

    Args:
        inputs: A float tensor of arbitrary shape.
                The predictions for each example.
        targets: A float tensor with the same shape as inputs. Stores the binary
                classification label for each element in inputs
                (0 for the negative class and 1 for the positive class).
        alpha: (optional) Weighting factor in range (0,1) to balance
                positive vs negative examples or -1 for ignore. Default = 0.25
        gamma: Exponent of the modulating factor (1 - p_t) to
               balance easy vs hard examples.
        reduction: 'none' | 'mean' | 'sum'
                 'none': No reduction will be applied to the output.
                 'mean': The output will be averaged.
                 'sum': The output will be summed.
    Returns:
        Loss tensor with the reduction option applied.
    """
    # if not torch.jit.is_scripting() and not torch.jit.is_tracing():
    #     _log_api_usage_once(sigmoid_focal_loss)
    p = torch.sigmoid(inputs)
    ce_loss = F.binary_cross_entropy_with_logits(inputs, targets, reduction="none")
    p_t = p * targets + (1 - p) * (1 - targets)
    loss = ce_loss * ((1 - p_t) ** gamma)

    if alpha >= 0:
        alpha_t = alpha * targets + (1 - alpha) * (1 - targets)
        loss = alpha_t * loss

    if reduction == "mean":
        loss = loss.mean()
    elif reduction == "sum":
        loss = loss.sum()

    return loss

dummy = torch.rand(10,8,3,712,680)
model = Pose_estimation_network(8,3)
out1,out2,out3,out4,out5,out6,out7 = model(dummy[0])
print(out1.shape)
X = dummy
Y1 = torch.rand(10,8,1,128,128)
Y2 = torch.rand(10,8,2,128,128)
Y3 = torch.rand(10,8,2,128,128)
Y4 = torch.rand(10,8,8,128,128)
Y5 = torch.rand(10,8,16,128,128)
Y6 = torch.rand(10,8,16,128,128)
Y7 = torch.rand(10,8,3,128,128)

import torch.optim as optim
loss_vector=[]
optimizer = optim.Adam(model.parameters(), lr=0.00007)

for epoch in range(10): # 3 full passes over the data
  #  model.train()
    for data in range(10):  # `data` is a batch of data
        train = X[data]
        model.zero_grad()  
        output = model.forward(train.float()) 
        
        loss_1 =  sigmoid_focal_loss(output[0],Y1[data].float())
        loss_2 = F.l1_loss(output[1], Y2[data], size_average=None, reduce=None, reduction='mean')
        loss_3 = F.l1_loss(output[2], Y3[data], size_average=None, reduce=None, reduction='mean')
        loss_4 =  sigmoid_focal_loss(output[3],Y4[data].float())
        loss_5 = F.l1_loss(output[4], Y5[data], size_average=None, reduce=None, reduction='mean')
        loss_6 = F.l1_loss(output[5], Y6[data], size_average=None, reduce=None, reduction='mean')
        loss_7 = F.l1_loss(output[6], Y7[data], size_average=None, reduce=None, reduction='mean')
        
        loss = loss_1+loss_2+loss_3+loss_4+loss_5+loss_6+loss_7
        loss.backward()  # apply this loss backwards thru the network's parameters
        optimizer.step()  # attempt to optimize weights to account for loss/gradients
    print(epoch,loss)
    loss_vector.append(loss)

Lv = [] 
for i in range(len(loss_vector)):
    Lv.append(loss_vector[i].item())
print(Lv)
plt.plot(Lv)
plt.xlabel("iteration")
plt.ylabel("loss")

plt.show()