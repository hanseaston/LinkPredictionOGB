# LinkPredictionOGB
Machine Learning for Big Data Project on Link Prediction. [Here](project_proposal.pdf) is a link to our formal project proposal.


### Papers:
1. [GraphSAGE](https://arxiv.org/pdf/1706.02216.pdf)
2. [GNN survey](https://arxiv.org/pdf/1901.00596.pdf)
3. [Link Prediction](http://www.eecs.harvard.edu/~michaelm/CS222/linkpred.pdf)
4. [Robustness of link prediction under noise](https://www.nature.com/articles/srep18881)
5. [SEAL](https://proceedings.neurips.cc/paper/2018/file/53f0d7c537d99b3824f0f99d62ea2428-Paper.pdf)

### Contributors:
1. William Howard-Snyder
2. Pallavi Banerjee
3. Therese Pena Pacio
4. Hans Easton

### Setup Instructions:
1. Clone the repo onto your machine with `git clone https://github.com/hanseaston/LinkPredictionOGB.git`
2. Navigate to the directory with `cd LinkPredictionOGB`
3. Create a new conda environment `conda env create --name link-pred --file environment.yml`
    - If you find pip requirements still missing, run `pip3 install -r requirements.txt`
    - `environment_no_build.yml` might be required instead, and the user may need to manually remove packages from the .yml file.
4. Implement your portion of the code in `models` and test your implementations in `experiments`


### Directory Structure:
1. dataset/
    - module for data pre-processing and analysis
    - direcotry for storing other data related info on disk (e.g., original graph)
2. experiments/
    - module for experiment files (training, testing)
3. models/
    - module for model definition files
4. results/
    - directory for storing link prediction results for each model/trial
