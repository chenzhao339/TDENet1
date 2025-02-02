# --------------------------------------------------------
# Pytorch Meta R-CNN
# Written by Anny Xu, Xiaopeng Yan, based on code from Jianwei Yang
# --------------------------------------------------------
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from model.utils.config import cfg
from model.faster_rcnn.faster_rcnn import _fasterRCNN

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable
from torch.nn import init
import math
import torch.utils.model_zoo as model_zoo
import pdb

__all__ = ['ResNet', 'resnet18', 'resnet34', 'resnet50', 'resnet101',
       'resnet152']


model_urls = {
  'resnet18': 'https://s3.amazonaws.com/pytorch/models/resnet18-5c106cde.pth',
  'resnet34': 'https://s3.amazonaws.com/pytorch/models/resnet34-333f7ec4.pth',
  'resnet50': 'https://s3.amazonaws.com/pytorch/models/resnet50-19c8e357.pth',
  'resnet101': 'https://s3.amazonaws.com/pytorch/models/resnet101-5d3b4d8f.pth',
  'resnet152': 'https://s3.amazonaws.com/pytorch/models/resnet152-b121ed2d.pth',
}

def conv3x3(in_planes, out_planes, stride=1):
  "3x3 convolution with padding"
  return nn.Conv2d(in_planes, out_planes, kernel_size=3, stride=stride,
           padding=1, bias=False)

def init_conv(conv,glu=True):
  init.xavier_uniform(conv.weight)
  if conv.bias is not None:
    conv.bias.data.zero_()

def init_linear(linear):
  init.constant(linear.weight,0)
  init.constant(linear.bias, 1)

class BasicBlock(nn.Module):
  expansion = 1

  def __init__(self, inplanes, planes, stride=1, downsample=None):
    super(BasicBlock, self).__init__()
    self.conv1 = conv3x3(inplanes, planes, stride)
    self.bn1 = nn.BatchNorm2d(planes)
    self.relu = nn.ReLU(inplace=True)
    self.conv2 = conv3x3(planes, planes)
    self.bn2 = nn.BatchNorm2d(planes)
    self.downsample = downsample
    self.stride = stride

  def forward(self, x):
    residual = x

    out = self.conv1(x)
    out = self.bn1(out)
    out = self.relu(out)

    out = self.conv2(out)
    out = self.bn2(out)

    if self.downsample is not None:
      residual = self.downsample(x)

    out += residual
    out = self.relu(out)

    return out

#封装成一个模块，方便重复使用
class Bottleneck(nn.Module):
  expansion = 4

  def __init__(self, inplanes, planes, stride=1, downsample=None):
    super(Bottleneck, self).__init__()
    self.conv1 = nn.Conv2d(inplanes, planes, kernel_size=1, stride=stride, bias=False) # change
    self.bn1 = nn.BatchNorm2d(planes)
    self.conv2 = nn.Conv2d(planes, planes, kernel_size=3, stride=1, # change
                 padding=1, bias=False)
    self.bn2 = nn.BatchNorm2d(planes)
    self.conv3 = nn.Conv2d(planes, planes * 4, kernel_size=1, bias=False)
    self.bn3 = nn.BatchNorm2d(planes * 4)
    self.relu = nn.ReLU(inplace=True)
    self.downsample = downsample
    self.stride = stride

#这里面有残差模块
  def forward(self, x):
    residual = x

    out = self.conv1(x)
    out = self.bn1(out)
    out = self.relu(out)

    out = self.conv2(out)
    out = self.bn2(out)
    out = self.relu(out)

    out = self.conv3(out)
    out = self.bn3(out)

    if self.downsample is not None:
      residual = self.downsample(x)

    out += residual
    out = self.relu(out)

    return out


class ResNet(nn.Module):
  def __init__(self, block, layers, num_classes=1000):
    #这里的inplanes是模型初始值，之后会变
    self.inplanes = 64
    super(ResNet, self).__init__()
    self.conv1 = nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3,
                 bias=False)
    self.bn1 = nn.BatchNorm2d(64)
    self.relu = nn.ReLU(inplace=True)
    self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=0, ceil_mode=True) # change
    self.layer1 = self._make_layer(block, 64, layers[0])
    self.layer2 = self._make_layer(block, 128, layers[1], stride=2)
    self.layer3 = self._make_layer(block, 256, layers[2], stride=2)
    self.layer4 = self._make_layer(block, 512, layers[3], stride=2)
    # it is slightly better whereas slower to set stride = 1
    # self.layer4 = self._make_layer(block, 512, layers[3], stride=1)
    self.avgpool = nn.AvgPool2d(7)
    self.fc = nn.Linear(512 * block.expansion, num_classes)

    for m in self.modules():
      if isinstance(m, nn.Conv2d):
        n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
        m.weight.data.normal_(0, math.sqrt(2. / n))
      elif isinstance(m, nn.BatchNorm2d):
        m.weight.data.fill_(1)
        m.bias.data.zero_()

  def _make_layer(self, block, planes, blocks, stride=1):
    downsample = None
    if stride != 1 or self.inplanes != planes * block.expansion:
      downsample = nn.Sequential(
        nn.Conv2d(self.inplanes, planes * block.expansion,
              kernel_size=1, stride=stride, bias=False),
        nn.BatchNorm2d(planes * block.expansion),
      )

    layers = []
    layers.append(block(self.inplanes, planes, stride, downsample))
    self.inplanes = planes * block.expansion
    for i in range(1, blocks):
      layers.append(block(self.inplanes, planes))

    return nn.Sequential(*layers)

  def forward(self, x):
    x = self.conv1(x)
    x = self.bn1(x)
    x = self.relu(x)
    x = self.maxpool(x)

    x = self.layer1(x)
    x = self.layer2(x)
    x = self.layer3(x)
    x = self.layer4(x)

    x = self.avgpool(x)
    x = x.view(x.size(0), -1)
    x = self.fc(x)

    return x


def resnet18(pretrained=False):
  """Constructs a ResNet-18 model.
  Args:
    pretrained (bool): If True, returns a model pre-trained on ImageNet
  """
  model = ResNet(BasicBlock, [2, 2, 2, 2])
  if pretrained:
    model.load_state_dict(model_zoo.load_url(model_urls['resnet18']))
  return model


def resnet34(pretrained=False):
  """Constructs a ResNet-34 model.
  Args:
    pretrained (bool): If True, returns a model pre-trained on ImageNet
  """
  model = ResNet(BasicBlock, [3, 4, 6, 3])
  if pretrained:
    model.load_state_dict(model_zoo.load_url(model_urls['resnet34']))
  return model


def resnet50(pretrained=False):
  """Constructs a ResNet-50 model.
  Args:
    pretrained (bool): If True, returns a model pre-trained on ImageNet
  """
  model = ResNet(Bottleneck, [3, 4, 6, 3])
  if pretrained:
    model.load_state_dict(model_zoo.load_url(model_urls['resnet50']))
  return model


def resnet101(pretrained=False):
  """Constructs a ResNet-101 model.
  Args:
    pretrained (bool): If True, returns a model pre-trained on ImageNet
  """
  model = ResNet(Bottleneck, [3, 4, 23, 3])
  if pretrained:
    model.load_state_dict(model_zoo.load_url(model_urls['resnet101']))
  return model


def resnet152(pretrained=False):
  """Constructs a ResNet-152 model.
  Args:
    pretrained (bool): If True, returns a model pre-trained on ImageNet
  """
  model = ResNet(Bottleneck, [3, 8, 36, 3])
  if pretrained:
    model.load_state_dict(model_zoo.load_url(model_urls['resnet152']))
  return model

#CZ:应该是说resnet类是fasterRCNN类的子类
class resnet(_fasterRCNN):
  def __init__(self, classes, num_layers=101, pretrained=False, class_agnostic=False,meta_train=True,meta_test=None,meta_loss=None):
    self.model_path = 'data/pretrained_model/resnet101_caffe.pth'
    self.dout_base_model = 1024
    self.pretrained = pretrained
    self.class_agnostic = class_agnostic
    self.meta_train = meta_train
    self.meta_test = meta_test
    self.meta_loss = meta_loss

    _fasterRCNN.__init__(self, classes, class_agnostic,meta_train,meta_test,meta_loss)

  def _init_modules(self):
    resnet = resnet101()

    if self.pretrained == True:
      print("Loading pretrained weights from %s" %(self.model_path))
      state_dict = torch.load(self.model_path)
      resnet.load_state_dict({k:v for k,v in state_dict.items() if k in resnet.state_dict()})

    # feat_dim = 4096
    feat_dim = 2048
    # Build resnet.
    self.meta_conv1 = nn.Conv2d(4, 64, kernel_size=7, stride=2, padding=3, bias=False)

    self.normal_meta_conv1 = nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3, bias=False)
    self.normal_meta_conv2 = nn.Conv2d(3, 64, kernel_size=9, stride=2, padding=4, bias=False)
    self.normal_meta_conv3 = nn.Conv2d(3, 64, kernel_size=11, stride=2, padding=5, bias=False)
    self.normal_meta_conv4 = nn.Conv2d(3, 64, kernel_size=13, stride=2, padding=6, bias=False)
    self.normal_meta_conv5 = nn.Conv2d(3, 64, kernel_size=15, stride=2, padding=7, bias=False)
    self.normal_meta_conv6 = nn.Conv2d(3, 64, kernel_size=17, stride=2, padding=8, bias=False)
    self.normal_meta_conv7 = nn.Conv2d(3, 64, kernel_size=19, stride=2, padding=9, bias=False)

    self.rcnn_conv1 = resnet.conv1

    self.RCNN_base = nn.Sequential(resnet.bn1,resnet.relu,
      resnet.maxpool,resnet.layer1,resnet.layer2,resnet.layer3)

    self.RCNN_top = nn.Sequential(resnet.layer4)

    self.sigmoid = nn.Sigmoid()
    self.softmax = nn.Softmax(dim=-1)

    self.max_pooled = nn.MaxPool2d(2)

    self.avg_pooled = nn.AvgPool2d(2)

    self.fc1 = nn.Linear(4096, 2048)

    self.RCNN_cls_score = nn.Linear(feat_dim, self.n_classes)

    if self.meta_loss:
      self.Meta_cls_score = nn.Linear(2048, self.n_classes)
      self.novel_cls_score1 = nn.Linear(2048, self.n_classes)

    if self.class_agnostic:
      self.RCNN_bbox_pred = nn.Linear(feat_dim, 4) # x,y,w,h
    else:
      self.RCNN_bbox_pred = nn.Linear(feat_dim, 4 * self.n_classes)


    # Fix blocks
    for p in self.rcnn_conv1.parameters(): p.requires_grad=False
    for p in self.RCNN_base[0].parameters(): p.requires_grad=False


    assert (0 <= cfg.RESNET.FIXED_BLOCKS < 5)
    if cfg.RESNET.FIXED_BLOCKS >= 4:
      for p in self.RCNN_top.parameters(): p.requires_grad = False
    if cfg.RESNET.FIXED_BLOCKS >= 3:
      for p in self.RCNN_base[5].parameters(): p.requires_grad=False
    if cfg.RESNET.FIXED_BLOCKS >= 2:
      for p in self.RCNN_base[4].parameters(): p.requires_grad=False
    if cfg.RESNET.FIXED_BLOCKS >= 1:
      for p in self.RCNN_base[3].parameters(): p.requires_grad=False

    def set_bn_fix(m):
      classname = m.__class__.__name__
      if classname.find('BatchNorm') != -1:
        for p in m.parameters(): p.requires_grad=False

    self.RCNN_base.apply(set_bn_fix)
    self.RCNN_top.apply(set_bn_fix)

  def train(self, mode=True):
    # Override train so that the training mode is set as we want
    nn.Module.train(self, mode)
    if mode:
      # Set fixed blocks to be in eval mode
      self.RCNN_base.eval()
      self.RCNN_base[4].train()
      self.RCNN_base[5].train()

      self.RCNN_base.eval()

      def set_bn_eval(m):
        classname = m.__class__.__name__
        if classname.find('BatchNorm') != -1:
          m.eval()

      self.RCNN_base.apply(set_bn_eval)
      self.RCNN_top.apply(set_bn_eval)

  def _head_to_tail(self, pool5):

    fc71 = self.RCNN_top(pool5)
    fc72 = fc71.mean(3)
    fc7 = fc72.mean(2)
    return fc7

  def prn_network(self,im_data):
    '''
    the Predictor-head Remodeling Network (PRN)
    :param im_data:
    :return attention vectors:
    '''
    #这里的最大池化的kenel-size为2,即为2×2的卷积核
    meta_feat = self.meta_conv1(im_data)
    base_feat = self.RCNN_base(meta_feat)
    maxpool_feat = self.max_pooled(base_feat)
    feature = self._head_to_tail(maxpool_feat)
    return feature


#这个地方有操作空间，可以编写一个不一样的模块
  def normal_prn_network(self,normal_data):
    '''
    the Predictor-head Remodeling Network (PRN)
    :param normal_data:
    :return attention vectors:
    '''
    meta_feat = self.normal_meta_conv4(normal_data.unsqueeze(0))
    base_feat = self.RCNN_base(meta_feat)
    maxpool_feat = self.max_pooled(base_feat)
    feature = self._head_to_tail(maxpool_feat)
    return feature


