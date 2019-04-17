import logging
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader


class Trainer(object):
    def __init__(self, model, memory, device, batch_size):
        """
        Train the trainable model of a policy
        """
        self.model = model
        self.device = device
        self.criterion = nn.MSELoss().to(device)
        self.memory = memory
        self.data_loader = None
        self.batch_size = batch_size
        self.optimizer = None

    def set_learning_rate(self, learning_rate):
        self.optimizer = optim.Adam(self.model.parameters(), lr=learning_rate)
        # self.optimizer = optim.SGD(self.model.parameters(), lr=learning_rate, momentum=0.9)
        logging.info('Lr: {} for parameters {} with Adam optimizer'.format(learning_rate, ' '.join(
            [name for name, param in self.model.named_parameters()])))

    def optimize_epoch(self, num_epochs, writer):
        if self.optimizer is None:
            raise ValueError('Learning rate is not set!')
        if self.data_loader is None:
            self.data_loader = DataLoader(self.memory, self.batch_size, shuffle=True, collate_fn=pad_batch)
        average_epoch_loss = 0
        for epoch in range(num_epochs):
            epoch_loss = 0
            for data in self.data_loader:
                inputs, values = data
                self.optimizer.zero_grad()
                outputs = self.model(inputs)
                loss = self.criterion(outputs, values)
                loss.backward()
                self.optimizer.step()
                epoch_loss += loss.data.item()
              
            average_epoch_loss = epoch_loss / len(self.memory)
            writer.add_scalar('IL/average_epoch_loss', average_epoch_loss, epoch)
            logging.info('Average loss in epoch %d: %.2E', epoch, average_epoch_loss)

        return average_epoch_loss

    def optimize_batch(self, num_batches):
        if self.optimizer is None:
            raise ValueError('Learning rate is not set!')
        if self.data_loader is None:
            self.data_loader = DataLoader(self.memory, self.batch_size, shuffle=True, collate_fn=pad_batch)
        losses = 0
        batch_count = 0
        for data in self.data_loader:
            inputs, values = data
            self.optimizer.zero_grad()
            outputs = self.model(inputs)
            loss = self.criterion(outputs, values)
            loss.backward()
            self.optimizer.step()
            losses += loss.data.item()

            batch_count += 1
            if batch_count > num_batches:
                break

        average_loss = losses / num_batches
        logging.debug('Average loss : %.2E', average_loss)

        return average_loss


def pad_batch(batch):
    """
    args:
        batch - list of (tensor, label)

    return:
        xs - a tensor of all examples in 'batch' after padding
        ys - a LongTensor of all labels in batch
    """
    # sort the sequences in the decreasing order of length
    sequences = sorted([x for x, y in batch], reverse=True, key=lambda x: x.size()[0])
    packed_sequences = torch.nn.utils.rnn.pack_sequence(sequences)
    xs = torch.nn.utils.rnn.pad_packed_sequence(packed_sequences, batch_first=True)
    ys = torch.Tensor([y for x, y in batch]).unsqueeze(1)

    return xs, ys
