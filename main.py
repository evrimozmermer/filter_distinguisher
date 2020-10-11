# -*- coding: utf-8 -*-
"""
Created on Sat Sep 26 20:38:55 2020

@author: evrim
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, transforms
import itertools
import numpy as np
import matplotlib.pyplot as plt
import cv2
from PIL import Image

class ConvLayer(torch.nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size, stride):
        super(ConvLayer, self).__init__()
        self.conv2d = torch.nn.Conv2d(in_channels, out_channels, kernel_size, stride)

    def forward(self, x):
        out = self.conv2d(x)
        return out

class SSNet(torch.nn.Module):
    def __init__(self,in_filters, out_filters):
        super(SSNet, self).__init__()
        self.conv1 = ConvLayer(in_filters, 64, kernel_size = 5, stride = 1)
        self.conv2 = ConvLayer(64, out_filters, kernel_size = 1, stride = 1)
        self.pool = nn.AvgPool2d(2, stride=2)
        self.relu = torch.nn.ReLU()
        
    def forward(self, x):
        out = self.pool(self.conv2(self.relu(self.conv1(x))))
        return out

class SSNetMultiple(torch.nn.Module):
    def __init__(self,levels = 5):
        super(SSNetMultiple, self).__init__()
        self.children = []
        for cnt in range(levels):
            if cnt == 0:
                in_filters, out_filters = 3,16
            elif cnt == levels-1:
                in_filters, out_filters = 16,16
            else:
                in_filters, out_filters = 16,16
            self.children.append(SSNet(in_filters, out_filters))
        
        self.main = nn.Sequential(*self.children)
        
    def forward(self, x, queue = 1):
        outs = [x]
        for cnt,child in enumerate(self.main):
            if cnt<queue:
                outs.append(child(outs[-1]))
        return outs[-1]

def normalize(vector):
    norm = vector.norm(p=2, dim=0, keepdim=True)
    vector_normalized = vector.div(norm.expand_as(vector))
    return vector_normalized

def sim_func(layers):
    combinations = list(itertools.combinations(np.arange(0,layers.shape[1]), 2))
    similarity_vector = torch.empty(len(combinations))
    for cnt,comb in enumerate(combinations):
        first = layers[0][comb[0]].flatten()
        second = layers[0][comb[1]].flatten()
        first_norm = normalize(first)
        second_norm = normalize(second)
        similarity_vector[cnt] = torch.matmul(first_norm,second_norm.T)
    return similarity_vector

def cam_to_tensor(cam):
    if cam.isOpened():
        ret, frame_ = cam.read()
    else:
        cam.release()
        cam = cv2.VideoCapture(video_source)
        ret, frame_ = cam.read()
    frame = cv2.cvtColor(frame_, cv2.COLOR_BGR2RGB)
    frame_pil = Image.fromarray(frame)
    image = transform(frame_pil)
    return image, frame_, cam

transform=transforms.Compose([
                            transforms.CenterCrop((360,360)),
                            transforms.Resize((224,224)),
                            transforms.ToTensor()
                            ])
#dataset = datasets.MNIST('../data',
#                         train=True,
#                         download=True,
#                         transform=transform)
model = SSNetMultiple(levels = 4)
try:
    model.load_state_dict(torch.load("./model_11_10_2020_city_video.pth"))
except:
    train = True
    model.train()
    
lr = 0.02
optimizer = optim.SGD(model.parameters(), lr=lr)
lossfunc = nn.MSELoss()

video_source = "./videoplayback.mp4"
cam = cv2.VideoCapture(video_source)

loss_obs = 0
epoch = 0
if train:
    while epoch<4:
    #    if epoch>0:
    #        for cc,param in enumerate(model.main[epoch-1].parameters()):
    #            print(epoch-1,"grad is deactivated")
    #            param.requires_grad = True
        for cnt in range(0,120000):
            image, _, cam = cam_to_tensor(cam)
            
            optimizer.zero_grad()
            out = model(image.unsqueeze(0), queue = epoch+1)
            sim_vec = sim_func(out)
            loss = lossfunc(sim_vec, torch.zeros(sim_vec.shape))
            loss_obs_ = torch.max(torch.abs(sim_vec-torch.zeros(sim_vec.shape)))
            loss_obs += loss_obs_
            loss.backward()
            optimizer.step()
            print("Epoch: {}\tSample: {}\tLoss: {}\tLR: {}".format(epoch,cnt,loss_obs_,optimizer.param_groups[0]["lr"]))
    
            if cnt%20 == 0 and cnt!=0:
                loss_obs = loss_obs/20
                print("Epoch: {}\tSample: {}\tLoss: {}\tLR: {}".format(epoch,cnt,loss_obs,optimizer.param_groups[0]["lr"]))
                if loss_obs<0.30:
                    epoch += 1
                    break
                loss_obs = 0

    torch.save(model.state_dict(), "./model_11_10_2020_city_video.pth")

def generate_embedding(model,cam,queue = 3):
    image, frame, _ = cam_to_tensor(cam)
    embedding = model(image.unsqueeze(0), queue = queue).flatten()
    return embedding, frame

def compare_samples(e1,e2):
    first_norm = normalize(e1.flatten())
    second_norm = normalize(e2.flatten())
    
    return torch.matmul(first_norm,second_norm.T).detach().numpy()


embedding_list = []
def compare_continuous(model,cam,queue):    
    font                   = cv2.FONT_HERSHEY_SIMPLEX
    bottomLeftCornerOfText = (10,100)
    fontScale              = 1
    fontColor              = (255,255,255)
    lineType               = 2
    
    cnt_f = 0
    while True:
        if cnt_f%300==0:
            e1, f1 = generate_embedding(model,cam,queue = queue)
            cv2.imshow('frame 1', f1)
        
        e2, f2 = generate_embedding(model,cam,queue = queue)
        embedding_list.append(e2.detach().numpy())
        embedding_list_np = np.array(embedding_list)
        std = np.std(embedding_list_np, axis=0)
        pca_idx = std.argsort()[-64:][::-1]
        
        e1_pca = e1[pca_idx.tolist()]
        e2_pca = e2[pca_idx.tolist()]
        
        sim = compare_samples(e1_pca,e2_pca)
        print(sim)
        
        cv2.putText(f2,'Similarity: {}'.format(sim), 
            bottomLeftCornerOfText, 
            font, 
            fontScale,
            fontColor,
            lineType)
        cv2.imshow('frame 2', f2)
        if cv2.waitKey(25) & 0xFF == ord('q'):
            break
        
        cnt_f += 1
    
compare_continuous(model,cam,queue=5)