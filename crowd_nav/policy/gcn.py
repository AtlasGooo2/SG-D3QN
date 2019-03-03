import torch
import torch.nn as nn
from torch.nn.functional import softmax, relu
import logging
from crowd_nav.policy.multi_human_rl import MultiHumanRL


class ValueNetwork(nn.Module):
    def __init__(self, input_dim, self_state_dim, num_layer):
        super().__init__()
        self.t_mlp = True
        self.planning_mlp = True
        self.expand_x = False

        human_state_dim = input_dim - self_state_dim
        self.self_state_dim = self_state_dim
        self.human_state_dim = human_state_dim
        self.num_layer = num_layer
        if self.t_mlp:
            self.t = nn.Sequential(nn.Linear(self_state_dim, 50),
                                   nn.ReLU(),
                                   nn.Linear(50, human_state_dim))
        else:
            self.t = torch.randn(self_state_dim, human_state_dim)
        self.w_a = torch.randn(human_state_dim, human_state_dim)
        if num_layer == 0:
            self.value_net = nn.Linear(human_state_dim, 1)
        elif num_layer == 1:
            self.w1 = torch.randn(human_state_dim, 64)
            if self.planning_mlp:
                self.value_net = nn.Sequential(nn.Linear(64, 64),
                                               nn.ReLU(),
                                               nn.Linear(64, 1))
            else:
                self.value_net = nn.Linear(64, 1)
        elif num_layer == 2:
            self.w1 = torch.randn(human_state_dim, 64)
            self.w2 = torch.randn(64, 64)
            if self.planning_mlp:
                self.value_net = nn.Sequential(nn.Linear(64, 64),
                                               nn.ReLU(),
                                               nn.Linear(64, 1))
            else:
                self.value_net = nn.Linear(64, 1)
        else:
            raise NotImplementedError

        # for visualization
        self.A = None

    def forward(self, state_input):
        if isinstance(state_input, tuple):
            state, lengths = state_input
        else:
            state = state_input
            # lengths = torch.IntTensor([state.size()[1]])

        self_state = state[:, 0, :self.self_state_dim]
        human_states = state[:, :, self.self_state_dim:]

        # compute feature matrix X
        if self.t_mlp:
            new_self_state = relu(self.t(self_state).unsqueeze(1))
        else:
            new_self_state = torch.matmul(self_state, self.t).unsqueeze(1)
        X = torch.cat([new_self_state, human_states], dim=1)

        # compute matrix A
        # w_a = self.w_a.expand((size[0],) + self.w_a.shape)
        # A = torch.exp(torch.matmul(torch.matmul(X, self.w_a), X.permute(0, 2, 1)))
        # normalized_A = A / torch.sum(A, dim=2, keepdim=True).expand_as(A)
        A = torch.matmul(torch.matmul(X, self.w_a), X.permute(0, 2, 1))
        normalized_A = torch.nn.functional.softmax(A, dim=2)
        self.A = normalized_A[0, :, :].data.cpu().numpy()

        def mm_ax(A, X, expand_x=False):
            if not expand_x:
                return torch.matmul(A, X)
            else:
                left = torch.reshape(torch.cat(X * X.size[1], dim=2), (X.size[0], -1, X.size[2]))
                right = torch.reshape(torch.cat(X * X.size[1], dim=1), (X.size[0], -1, X.size[2]))
                X_prime = torch.cat([left, right], dim=2)
                A_prime = ...

        # graph convolution
        if self.num_layer == 0:
            feat = X[:, 0, :]
        elif self.num_layer == 1:
            h1 = relu(torch.matmul(mm_ax(normalized_A, X, self.expand_x), self.w1))
            feat = h1[:, 0, :]
        else:
            # compute h1 and h2
            h1 = relu(torch.matmul(mm_ax(normalized_A, X, self.expand_x), self.w1))
            h2 = relu(torch.matmul(torch.matmul(normalized_A, h1), self.w2))
            feat = h2[:, 0, :]

        # do planning using only the final layer feature of the agent
        value = self.value_net(feat)
        return value


class GCN(MultiHumanRL):
    def __init__(self):
        super().__init__()
        self.name = 'GCN'

    def configure(self, config):
        self.multiagent_training = config.gcn.multiagent_training
        num_layer = config.gcn.num_layer
        self.set_common_parameters(config)
        self.model = ValueNetwork(self.input_dim(), self.self_state_dim, num_layer)
        logging.info('GCN layers: {}'.format(num_layer))
        logging.info('Policy: {}'.format(self.name))

    def get_matrix_A(self):
        return self.model.A