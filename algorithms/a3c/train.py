"""
Adapted from https://github.com/ikostrikov/pytorch-a3c
"""

import torch
import torch.nn.functional as F
import torch.optim as optim
from torch.autograd import Variable

from envs import create_atari_env
from gym_ai2thor.envs.ai2thor_env import AI2ThorEnv
from model import ActorCritic


def ensure_shared_grads(model, shared_model):
    for param, shared_param in zip(model.parameters(),
                                   shared_model.parameters()):
        if shared_param.grad is not None:
            return
        shared_param._grad = param.grad


def train(rank, args, shared_model, counter, lock, optimizer=None):
    torch.manual_seed(args.seed + rank)

    if args.atari:
        env = create_atari_env(args.atari_env_name)
    else:
        args.config_dict = {'max_episode_length': args.max_episode_length}
        env = AI2ThorEnv(config_dict=args.config_dict)
    env.seed(args.seed + rank)

    model = ActorCritic(env.observation_space.shape[0], env.action_space.n, args.frame_dim)

    if optimizer is None:
        optimizer = optim.Adam(shared_model.parameters(), lr=args.lr)

    model.train()

    state = env.reset()
    state = torch.from_numpy(state)
    done = True

    # monitoring
    total_reward_for_num_steps_list = []
    episode_total_rewards_list = []
    all_rewards_in_episode = []
    avg_reward_for_num_steps_list = []

    total_length = 0
    episode_length = 0
    while True:
        # Sync with the shared model
        model.load_state_dict(shared_model.state_dict())
        if done:
            cx = Variable(torch.zeros(1, 256))
            hx = Variable(torch.zeros(1, 256))
        else:
            cx = Variable(cx.data)
            hx = Variable(hx.data)

        values = []
        log_probs = []
        rewards = []
        entropies = []

        for step in range(args.num_steps):
            episode_length += 1
            total_length += 1
            value, logit, (hx, cx) = model((Variable(state.unsqueeze(0).float()), (hx, cx)))
            prob = F.softmax(logit)
            log_prob = F.log_softmax(logit)
            entropy = -(log_prob * prob).sum(1, keepdim=True)
            entropies.append(entropy)

            action = prob.multinomial(num_samples=1).data
            log_prob = log_prob.gather(1, Variable(action))

            action_int = action.numpy()[0][0].item()
            state, reward, done, _ = env.step(action_int)

            done = done or episode_length >= args.max_episode_length

            with lock:
                counter.value += 1

            if done:
                episode_length = 0
                total_length -= 1
                total_reward_for_episode = sum(all_rewards_in_episode)
                episode_total_rewards_list.append(total_reward_for_episode)
                all_rewards_in_episode = []
                state = env.reset()
                print('Episode Over. Total Length: {}. Total reward for episode: {}'.format(
                                            total_length,  total_reward_for_episode))
                print('Step no: {}. total length: {}'.format(episode_length, total_length))

            state = torch.from_numpy(state)
            values.append(value)
            log_probs.append(log_prob)
            rewards.append(reward)
            all_rewards_in_episode.append(reward)

            if done:
                break

        # No interaction with environment below.
        # Monitoring
        total_reward_for_num_steps = sum(rewards)
        total_reward_for_num_steps_list.append(total_reward_for_num_steps)
        avg_reward_for_num_steps = total_reward_for_num_steps / len(rewards)
        avg_reward_for_num_steps_list.append(avg_reward_for_num_steps)

        # Backprop and optimisation
        R = torch.zeros(1, 1)
        if not done:  # to change last reward to predicted value to ....
            value, _, _ = model((Variable(state.unsqueeze(0).float()), (hx, cx)))
            R = value.data

        values.append(Variable(R))
        policy_loss = 0
        value_loss = 0
        # import pdb;pdb.set_trace() # good place to breakpoint to see training cycle
        R = Variable(R)
        gae = torch.zeros(1, 1)
        for i in reversed(range(len(rewards))):
            R = args.gamma * R + rewards[i]
            advantage = R - values[i]
            value_loss = value_loss + 0.5 * advantage.pow(2)

            # Generalized Advantage Estimation
            delta_t = rewards[i] + args.gamma * \
                values[i + 1].data - values[i].data
            gae = gae * args.gamma * args.tau + delta_t

            policy_loss = policy_loss - \
                log_probs[i] * Variable(gae) - args.entropy_coef * entropies[i]

        optimizer.zero_grad()

        (policy_loss + args.value_loss_coef * value_loss).backward()
        torch.nn.utils.clip_grad_norm(model.parameters(), args.max_grad_norm)

        ensure_shared_grads(model, shared_model)
        optimizer.step()