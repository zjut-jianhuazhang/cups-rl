
import time
from pprint import pprint
import random

import numpy as np
import skimage.color, skimage.transform
import matplotlib as mpl
mpl.use('TkAgg')  # or whatever other backend that you want
#mpl.use('Agg')  # or whatever other backend that you want
from matplotlib import pyplot as plt
import matplotlib.patches as patches
import ai2thor.controller

from envs import ThorWrapperEnv

if __name__ == '__main__':
    #

    actions_to_look_at_microwave = [6, 6, 0, 0, 6, 0, 7, 0, 0, 0, 0, 7, 2, 8, 8, 8, 8, 1]
    actions_to_look_at_cup = [6, 6, 0, 0, 6, 0, 0, 7, 0, 0, 0, 7, 5]

    env = ThorWrapperEnv(natural_language_instruction=True)
    for episode in range(2):
        env.current_instruction_idx = 0
        env.current_object_type = 'Microwave'
        for idx, a in enumerate(actions_to_look_at_microwave):
            s, r, terminal = env.step(a)
            print(r, terminal)
            if terminal:
                break
            # time.sleep(0.5)

        env.reset()
        env.current_instruction_idx = 1
        env.current_object_type = 'Mug'
        for idx, a in enumerate(actions_to_look_at_cup):
            s, r, terminal = env.step(a)
            print(r, terminal)
            if terminal:
                break

        env.reset()
        time.sleep(2)
