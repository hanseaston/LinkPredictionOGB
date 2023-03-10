import sys
import os
sys.path.append(os.getcwd())
#####################################################################

from models.GraphSAGE import GraphSAGE
from models.Neighborhood import CommonNeighbor, AdamicAdar, RuntimeCN
from models.RandomWalkMLP import RandomWalkMLP

# NOTE: Need to add this to the conda env
# from models.RandomWalk import Node2Vec

from ogb.linkproppred import Evaluator

import pandas as pd
import numpy as np
import networkx as nx

from dataset.utils import load_data
import time

TRAIN = True


model_types = [
    # (GraphSAGE, "graphsage"),
    # (RuntimeCN, "runtime_cn"),
    # (AdamicAdar, "adamicadar"),
    (RandomWalkMLP, "randomwalk")
]

# perturb_list = [("remove", 0.1), ("remove", 0.25), ("remove", 0.5),
#                 ("add", 0.1), ("add", 0.25), ("add", 0.5)]

# NOTE: Currently running both of these (in separate terminals) as of 3/8 8:00 am on the cloud
# TODO: Add seems to be getting destroyed. Retry these with remove instead of add
# perturb_list = [("remove", 0.1), ("add", 0.1)]
perturb_list = [("add", 0.0)]

def main():

    perturb_dir = "dataset/perturbation"

    # need this for validation set
    _, split_edge_tensor = load_data(test_as_tensor=True)
    _, split_edge_list = load_data()

    for perturb_type in ["adversial"]:
        for change, prop in perturb_list:
            
            data_path = perturb_dir + f"/{perturb_type}_{change}_{prop}.csv"

            if prop == 0.0:
                G, _ = load_data()
            else:
                G, _ = load_data(perturbation_path=data_path)

            for LinkPredictor, name in model_types:
                start = time.time()

                out_path = f"results/{perturb_type}/{change}/{prop}"
                os.makedirs(out_path, exist_ok=True)
                
                model = LinkPredictor()

                if TRAIN:
                    print(f"==> Training {name}: {perturb_type} {change} {prop}")

                    if name == "graphsage":
                        model.train(G, val_edges=split_edge_tensor["valid"], out_path=out_path)
                        
                        # NOTE: Load best performing model from gnn_trained directory and use
                        #       that for testing
                        load_path = f"{out_path}/gnn_trained"
                        print("=>", load_path)
                        if not os.path.isdir(f"{load_path}"):
                            print(f"\n\nDoes not exist: {load_path}\n")
                            continue
                        path_list = os.listdir(load_path)
                        # Use string formatting to get the latest epoch
                        path_list.sort(key = lambda pth: int(pth[2:-7]))
                        print("\tBest model:", path_list[-1])
                        model.load_model(f"{load_path}/{path_list[-1]}")
                        model.save_model(out_path)

                    elif name == "randomwalk":
                        embedding_path = f"models/RandomWalkEmbeddings/adversial_{change}_{prop}.pt"
                        model.train(graph=G, val_edges=split_edge_tensor["valid"], embedding_path=embedding_path, out_path=out_path)
                        load_path = f"{out_path}/randomwalk_trained"
                        print("=>", load_path)
                        if not os.path.isdir(f"{load_path}"):
                            print(f"\n\nDoes not exist: {load_path}\n")
                            continue
                        path_list = os.listdir(load_path)
                        # Use string formatting to get the latest epoch
                        path_list.sort(key = lambda pth: int(pth[2:-7]))
                        print("\tBest model:", path_list[-1])
                        model.load_model(f"{load_path}/{path_list[-1]}")
                        model.save_model(out_path)

                    else:
                        model.train(G)
                    model.save_model(out_path)

                print(f"==> Testing")
                model.load_model(out_path)

                if name == "graphsage" or name == "randomwalk":
                    split_edge = split_edge_tensor
                else:
                    split_edge = split_edge_list
                

                pos_valid_preds = model.score_edges(split_edge["valid"]["edge"])
                neg_valid_preds = model.score_edges(split_edge["valid"]["edge_neg"])

                pos_test_pred = model.score_edges(split_edge["test"]["edge"])
                neg_test_pred = model.score_edges(split_edge["test"]["edge_neg"])
                print("\tEdges scored")

                evaluator = Evaluator(name='ogbl-ddi')
                results = {}

                # metrics on validation test
                for K in [20, 50, 100]:
                    evaluator.K = K
                    hits = evaluator.eval({
                        'y_pred_pos': np.array(pos_valid_preds),
                        'y_pred_neg': np.array(neg_valid_preds),
                    })[f'hits@{K}']

                    results[f'Hits@{K}'] = hits

                print("\tVal scoring evaluated")
                print(results)
                
                with open(f"{out_path}/{name}_final.txt", 'w') as f:
                    f.write("On validation set, model achieves:\n")
                    f.write(str(results) + "\n\n")

                # metrics on test test
                for K in [20, 50, 100]:
                    evaluator.K = K
                    hits = evaluator.eval({
                        'y_pred_pos': np.array(pos_test_pred),
                        'y_pred_neg': np.array(neg_test_pred),
                    })[f'hits@{K}']

                    results[f'Hits@{K}'] = hits
                
                with open(f'{out_path}/{name}_final.txt', 'a') as f:
                    f.write("On test set, model achieves:\n")
                    f.write(str(results))
                print(results)

    end = time.time()

    print(f"\tScript took {round((end - start) / 60, 2)} minutes to run")


def train():
    """
    Trains and saves model using abstract class methods
    """
    print("=> Preparing dataset...")
    G, split_edge = load_data(test_as_tensor=True)

    print("=> Initializing model...")
    model = GraphSAGE()

    print("=> Training model...")
    model.train(G, val_edges=split_edge["val"])

    print("=> Saving model...")
    model.save_model()



def load_test():
    """
    Loads and tests model using abstract class methods
    """
    print("=> Preparing dataset...")
    _, split_edge = load_data()

    print("=> Initializing model...")
    model = GraphSAGE()

    print("=> Loading model...")
    # NOTE: The ep440 gnn does not have edge_index. Need to re-save the ep440 by
    # assigning it ep330 edge index
    model.load_model("models/trained_model_files/graphsage/_gnn_dict_ep330.pt")
    
    print("=> Testing model...")

    pos_valid_preds = model.score_edges(split_edge["valid"]["edge"])
    neg_valid_preds = model.score_edges(split_edge["valid"]["edge_neg"])

    pos_test_pred = model.score_edges(split_edge["test"]["edge"])
    neg_test_pred = model.score_edges(split_edge["test"]["edge_neg"])

    evaluator = Evaluator(name='ogbl-ddi')
    results = {}

    # metrics on validation test
    for K in [20, 50, 100]:
        evaluator.K = K
        hits = evaluator.eval({
            'y_pred_pos': np.array(pos_valid_preds),
            'y_pred_neg': np.array(neg_valid_preds),
        })[f'hits@{K}']

        results[f'Hits@{K}'] = hits
    
    with open(f"results/graphsage.txt", 'w') as f:
        f.write("On validation set, model achieves:\n")
        f.write(str(results) + "\n\n")

    # metrics on test test
    for K in [20, 50, 100]:
        evaluator.K = K
        hits = evaluator.eval({
            'y_pred_pos': np.array(pos_test_pred),
            'y_pred_neg': np.array(neg_test_pred),
        })[f'hits@{K}']

        results[f'Hits@{K}'] = hits
    
    with open(f'results/graphsage.txt', 'a') as f:
        f.write("On test set, model achieves:\n")
        f.write(str(results))



if __name__ == "__main__":
    main()
