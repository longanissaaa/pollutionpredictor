from sklearn.datasets import load_iris
import pandas as pd
import numpy as np


iris = load_iris()

x = iris.data
y = iris.target

def get_species_data(x,y, samples):
    species_data = {}
    for label, name in enumerate (iris.target_names):
        idx = np.where(y == label)[0][:samples]
        species_data[name] = (x[idx],y[idx])
    return species_data

species_data = get_species_data(x,y,30)

setosa_X, setosa_y = species_data['setosa']
versicolor_X, versicolor_y = species_data['versicolor']
virginica_X, virginica_y = species_data['virginica']

print(setosa_X.shape, versicolor_X.shape, virginica_X.shape)