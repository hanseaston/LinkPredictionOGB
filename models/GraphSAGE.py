from models.LinkPredModel import LinkPredictor

class GraphSAGE(LinkPredictor):

    def __init__(self) -> None:
        super().__init__()

        # Model modules that will need to be loaded after training
        # These contain parameters that define our link prediction function
        self.emb = None
        self.model = None
        self.link_predictor = None

    
    def train(self, graph, val_edges=None, epochs=500, hidden_dim=256, num_layers=2, dropout=0.3, lr = 3e-3,
              node_emb_dim = 256, batch_size = 64 * 1024):
        """
        Trains the GNN model
        graph: networkx graph of training data
        val_edges: dictionary with positive edges on `edge` and negative edges at `neg_edge`
        """
        
        num_nodes = graph.number_of_nodes()
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        optim_wd = 0

        # Convert input graph into something that can be used by PyTorch
        #   - pos_train_edge (PE x 2) tensor of edges
        #   - edge_idx (2 x E) tensor of edges

        pos_list = []
        edge_list = [[], []]
        seen_nodes = set()

        for node, nbr_dict in graph.adjacency():
            seen_nodes.add(node)
            for n in nbr_dict.keys():
                if n not in seen_nodes:
                    pos_list.append([node, n])
                edge_list[0].append(int(node))
                edge_list[0].append(int(n))
                edge_list[1].append(int(n))
                edge_list[1].append(int(node))

        # pos_train_edge = torch.tensor(pos_list, dtype=torch.uint8).to(device)
        # edge_index = torch.tensor(edge_list, dtype=torch.uint8).to(device)

        pos_train_edge = torch.tensor(pos_list).to(device)
        edge_index = torch.tensor(edge_list).to(device)

        if val_edges is not None:
            pos_val_edges = val_edges["edge"]
            neg_val_edges = val_edges["edge_neg"]
            # val_edges = torch.Tensor(val_edges).to(device)


        evaluator = Evaluator(name='ogbl-ddi')

        # Node embeddings that must be learned
        self.emb = torch.nn.Embedding(num_nodes, node_emb_dim).to(device)
        # GNN uses message passing to aggregate node embeddings
        self.model = GNNStack(node_emb_dim, hidden_dim, hidden_dim, num_layers, dropout, emb=True).to(device)
        # MLP that takes embeddings of a pair of nodes and predicts whether there is an edge
        self.link_predictor = LinkPredictor(hidden_dim, hidden_dim, 1, num_layers + 1, dropout).to(device)

        # Jointly optimize all 3 components
        optimizer = torch.optim.Adam(
            list(self.model.parameters()) + list(self.link_predictor.parameters()) + list(self.emb.parameters()),
            lr=lr, weight_decay=optim_wd
        )

        train_loss = []
        val_hits = []
        max_val = -1
        for e in range(epochs):
            loss = train(self.model, self.link_predictor, self.emb.weight, edge_index, pos_train_edge, batch_size, optimizer)
            print(f"Epoch {e + 1}: loss: {round(loss, 5)}")
            train_loss.append(loss)

            if val_edges is not None:
                result = test(self.model, self.link_predictor, self.emb.weight, edge_index, pos_val_edges, neg_val_edges, batch_size, evaluator)
                val_performance = result['Hits@20']
                val_hits.append(val_performance)
                if (e+1)%10 ==0:
                    print(result)
                if val_performance > max_val:
                    self.save_model()
                    max_val = val_performance
                    print("=> max val =", max_val)

        # TODO: Save loss info + plots
        import matplotlib.pyplot as plt
        import numpy as np
        plt.title('Link Prediction on OGB-ddi using GraphSAGE GNN')
        plt.plot(train_loss,label="training loss")
        plt.plot(np.arange(len(val_hits)),val_hits,label="Hits@20 on validation")
        plt.xlabel('Epochs')
        plt.legend()
        plt.savefig("training_link_pred.png")

        print("Best val performance is", max_val)

        return None

    def score_edge(self, node1, node2):
        print("Not implemented")
        return 0.0
    
    def save_model(self):
        # NOTE: This assumes you're running the command from LinkPredicitonOGB directory
        torch.save({
            "emb": self.emb,
            "model": self.model,
            "link_predictor": self.link_predictor
        }, "models/trained_model_files/gnn_dict.pt")
    
    def load_model(self):
        model_dict = torch.load("models/trained_model_files/gnn_dict.pt")
        self.emb = model_dict["emb"]
        self.model = model_dict["model"]
        self.link_predictor = model_dict["link_predictor"]



#######################################################
### Defining pytorch components for model architecture
#######################################################

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch_geometric as pyg
from torch_geometric.data import DataLoader
from torch_geometric.utils import negative_sampling
from ogb.linkproppred import PygLinkPropPredDataset, Evaluator

# Implementation largely taken from this repository:
# https://github.com/samar-khanna/cs224w-project

class GNNStack(torch.nn.Module):
    def __init__(self, input_dim, hidden_dim, output_dim, num_layers, dropout, emb=False):
        super(GNNStack, self).__init__()
        conv_model = pyg.nn.SAGEConv

        self.convs = nn.ModuleList()
        self.convs.append(conv_model(input_dim, hidden_dim))
        self.dropout = dropout
        self.num_layers = num_layers
        self.emb = emb

        # Create num_layers GraphSAGE convs
        assert (self.num_layers >= 1), 'Number of layers is not >=1'
        for l in range(self.num_layers - 1):
            self.convs.append(conv_model(hidden_dim, hidden_dim))

        # post-message-passing processing is a two layer MLP
        self.post_mp = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.Dropout(self.dropout),
            nn.Linear(hidden_dim, output_dim))

    def forward(self, x, edge_index):
        """
        Applies this module's graph convolutions to the given data
            x: Node embeddings
            edge_index: Edges to use in convolutional layers
        """
        for i in range(self.num_layers):
            x = self.convs[i](x, edge_index)
            x = F.relu(x)
            x = F.dropout(x, p=self.dropout, training=self.training)

        x = self.post_mp(x)

        # Return final layer of embeddings if specified
        if self.emb:
            return x

        # Else return class probabilities
        return F.log_softmax(x, dim=1)

    def loss(self, pred, label):
        return F.nll_loss(pred, label)


class LinkPredictor(nn.Module):
    """
    Simple funciton that element-wise multiplies node embeddigns and applies MLP to result
    """
    def __init__(self, in_channels, hidden_channels, out_channels, num_layers,
                 dropout):
        super(LinkPredictor, self).__init__()

        # Create linear layers
        self.lins = nn.ModuleList()
        self.lins.append(nn.Linear(in_channels, hidden_channels))
        for _ in range(num_layers - 2):
            self.lins.append(nn.Linear(hidden_channels, hidden_channels))
        self.lins.append(nn.Linear(hidden_channels, out_channels))

        self.dropout = dropout

    def reset_parameters(self):
        for lin in self.lins:
            lin.reset_parameters()

    def forward(self, x_i, x_j):
        # x_i and x_j are both of shape (E, D)
        x = x_i * x_j
        for lin in self.lins[:-1]:
            x = lin(x)
            x = F.relu(x)
            x = F.dropout(x, p=self.dropout, training=self.training)
        x = self.lins[-1](x)
        return torch.sigmoid(x)



def train(model, link_predictor, emb, edge_index, pos_train_edge, batch_size, optimizer):
    """
    Runs offline training for model, link_predictor and node embeddings given the message
    edges and supervision edges.
    :param model: Torch Graph model used for updating node embeddings based on message passing
    :param link_predictor: Torch model used for predicting whether edge exists or not
    :param emb: (N, d) Initial node embeddings for all N nodes in graph
    :param edge_index: (2, E) Edge index for all edges in the graph
    :param pos_train_edge: (PE, 2) Positive edges used for training supervision loss
    :param batch_size: Number of positive (and negative) supervision edges to sample per batch
    :param optimizer: Torch Optimizer to update model parameters
    :return: Average supervision loss over all positive (and correspondingly sampled negative) edges
    """
    model.train()
    link_predictor.train()

    train_losses = []

    for edge_id in DataLoader(range(pos_train_edge.shape[0]), batch_size, shuffle=True):
        optimizer.zero_grad()

        # Run message passing on the inital node embeddings to get updated embeddings
        node_emb = model(emb, edge_index)  # (N, d)

        # Predict the class probabilities on the batch of positive edges using link_predictor
        pos_edge = pos_train_edge[edge_id].T  # (2, B)
        pos_pred = link_predictor(node_emb[pos_edge[0]], node_emb[pos_edge[1]])  # (B, )

        # Sample negative edges (same number as number of positive edges) and predict class probabilities 
        neg_edge = negative_sampling(edge_index, num_nodes=emb.shape[0],
                                     num_neg_samples=edge_id.shape[0], method='dense')  # (Ne,2)
        neg_pred = link_predictor(node_emb[neg_edge[0]], node_emb[neg_edge[1]])  # (Ne,)

        # Compute the corresponding negative log likelihood loss on the positive and negative edges
        loss = -torch.log(pos_pred + 1e-15).mean() - torch.log(1 - neg_pred + 1e-15).mean()

        # Backpropagate and update parameters
        loss.backward()
        optimizer.step()

        train_losses.append(loss.item())
    return sum(train_losses) / len(train_losses)


# TODO: This might be able to evaluate any method...
def test(model, predictor, emb, edge_index, pos_edge, neg_edge, batch_size, evaluator):
    """
    Evaluates graph model on validation and test edges
    :param model: Torch Graph model used for updating node embeddings based on message passing
    :param predictor: Torch model used for predicting whether edge exists or not
    :param emb: (N, d) Initial node embeddings for all N nodes in graph
    :param edge_index: (2, E) Edge index for all edges in the graph
    :param pos_edge: Tensor of (e, 2) edges for testing
    :param batch_size: Number of positive (and negative) supervision edges to sample per batch
    :param evaluator: OGB evaluator to calculate hits @ k metric
    :return: hits @ k results
    """
    model.eval()
    predictor.eval()

    node_emb = model(emb, edge_index)

    pos_edge.to(emb.device)
    neg_edge.to(emb.device)

    pos_preds = []
    for perm in DataLoader(range(pos_edge.size(0)), batch_size):
        edge = pos_edge[perm].t()
        pos_preds += [predictor(node_emb[edge[0]], node_emb[edge[1]]).squeeze().cpu()]
    pos_pred = torch.cat(pos_preds, dim=0)

    neg_preds = []
    for perm in DataLoader(range(neg_edge.size(0)), batch_size):
        edge = neg_edge[perm].t()
        neg_preds += [predictor(node_emb[edge[0]], node_emb[edge[1]]).squeeze().cpu()]
    neg_pred = torch.cat(neg_preds, dim=0)


    results = {}
    for K in [20, 50, 100]:
        evaluator.K = K
        hits = evaluator.eval({
            'y_pred_pos': pos_pred,
            'y_pred_neg': neg_pred,
        })[f'hits@{K}']

        results[f'Hits@{K}'] = hits

    return results

