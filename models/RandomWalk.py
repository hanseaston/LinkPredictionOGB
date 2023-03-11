import sys
import os
sys.path.append(os.getcwd())
#####################################################################

import argparse
import torch
from torch_geometric.nn import Node2Vec
from dataset.utils import load_data



def save_embedding(model, embedding_file_path):
    torch.save(model.embedding.weight.data.cpu(), embedding_file_path)

# extract the edge indices of the graph, and convert it to pytorch tensor
def extract_edge_index(graph, device):
    edge_list = [[], []]
    seen_nodes = set()

    for node, nbr_dict in graph.adjacency():
        seen_nodes.add(node)
        for n in nbr_dict.keys():
            edge_list[0].append(int(node))
            edge_list[0].append(int(n))
            edge_list[1].append(int(n))
            edge_list[1].append(int(node))

    edge_index = torch.tensor(edge_list).to(device)
    return edge_index


def start_random_walk(graph, file_name):

    # Note: for now, we only use the default arguments to train random walk
    parser = argparse.ArgumentParser(description='OGBL-DDI (Node2Vec)')
    parser.add_argument('--device', type=int, default=0)
    parser.add_argument('--embedding_dim', type=int, default=128)
    parser.add_argument('--walk_length', type=int, default=40)
    parser.add_argument('--context_size', type=int, default=20)
    parser.add_argument('--walks_per_node', type=int, default=10)
    parser.add_argument('--batch_size', type=int, default=256)
    parser.add_argument('--lr', type=float, default=0.01)
    parser.add_argument('--epochs', type=int, default=50)
    parser.add_argument('--log_steps', type=int, default=1)
    args = parser.parse_args()

    device = f'cuda:{args.device}' if torch.cuda.is_available() else 'cpu'
    device = torch.device(device)

    edge_index = extract_edge_index(graph, device)

    model = Node2Vec(edge_index, args.embedding_dim, args.walk_length,
                     args.context_size, args.walks_per_node,
                     sparse=True).to(device)

    loader = model.loader(batch_size=args.batch_size, shuffle=True,
                          num_workers=4)
    optimizer = torch.optim.SparseAdam(list(model.parameters()), lr=args.lr)

    model.train()

    for epoch in range(1, args.epochs + 1):
        for i, (pos_rw, neg_rw) in enumerate(loader):
            optimizer.zero_grad()
            loss = model.loss(pos_rw.to(device), neg_rw.to(device))
            loss.backward()
            optimizer.step()

            if (i + 1) % args.log_steps == 0:
                print(f'Epoch: {epoch:02d}, Step: {i+1:03d}/{len(loader)}, '
                      f'Loss: {loss:.4f}')

            if (i + 1) % 100 == 0:  # Save model every 100 steps.
                save_embedding(model, file_name)
        save_embedding(model, file_name)

if __name__ == "__main__":
    percentages = [0.5]
    for percentage in percentages:
        edge_file_path = f"dataset/perturbation/adversial_remove_{percentage}.csv"
        embedding_file_path = f"models/RandomWalkEmbeddings/adversial_remove_{percentage}.pt"
        print(f"searching for edge csv file in {edge_file_path}")
        G, _ = load_data(edge_file_path)
        start_random_walk(G, embedding_file_path)