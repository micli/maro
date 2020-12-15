# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

import sys
from abc import ABC, abstractmethod
from typing import Callable

from maro.communication import Proxy, RegisterTable, SessionMessage, SessionType
from maro.rl.agent.abs_agent_manager import AbsAgentManager
from maro.rl.scheduling.scheduler import Scheduler
from maro.utils import DummyLogger, Logger

from .common import Component, MessageTag, PayloadKey

ACTOR = Component.ACTOR.value


class AbsDistLearner(ABC):
    """Abstract distributed learner class.

    Args:
        agent_manager (AbsAgentManager): An AgentManager instance that manages all agents.
        scheduler (AbsScheduler): A scheduler responsible for iterating over episodes and generating exploration
            parameters if necessary.
        experience_collection_func (Callable): Function to collect experiences from multiple remote actors.
        update_trigger (str): Number or percentage of ``MessageTag.FINISHED`` messages required to trigger
            the ``_update`` method, i.e., model training.
        logger (Logger): Used to log important messages.
        proxy_params: Parameters required for instantiating an internal proxy for communication.
    """
    def __init__(
        self,
        agent_manager: AbsAgentManager,
        scheduler: Scheduler,
        experience_collecting_func: Callable,
        update_trigger: str = None,
        logger: Logger = DummyLogger(),
        **proxy_params
    ):
        super().__init__()
        self._agent_manager = agent_manager
        self._scheduler = scheduler
        self._experience_collecting_func = experience_collecting_func
        self._proxy = Proxy(component_type=Component.LEARNER.value, **proxy_params)
        self._registry_table = RegisterTable(self._proxy.peers_name)
        self._actors = self._proxy.peers_name[ACTOR]
        if update_trigger is None:
            update_trigger = len(self._actors)
        self._registry_table.register_event_handler(
            f"{ACTOR}:{MessageTag.FINISHED.value}:{update_trigger}", self._update
        )
        self._logger = logger
        self._pending_actor_set = None

    @abstractmethod
    def learn(self):
        raise NotImplementedError

    @abstractmethod
    def test(self):
        return NotImplementedError

    def exit(self):
        """Tell the remote actor to exit."""
        self._proxy.ibroadcast(
            component_type=Component.ACTOR.value, tag=MessageTag.EXIT, session_type=SessionType.NOTIFICATION
        )
        sys.exit(0)

    def load_models(self, dir_path: str):
        self._agent_manager.load_models_from_files(dir_path)

    def dump_models(self, dir_path: str):
        self._agent_manager.dump_models_to_files(dir_path)

    def _request_rollout(self, episode: str):
        """Send roll-out requests to remote actors.

        Args:
            episode (str): A string indicating the current training episode or the test phase if equal to "test".

        """
        self._pending_actor_set = set(self._actors)
        self._proxy.ibroadcast(
            component_type=ACTOR,
            tag=MessageTag.ROLLOUT,
            session_id=episode,
            session_type=SessionType.TASK
        )

    def _update(self, messages: list):
        if isinstance(messages, SessionMessage):
            messages = [messages]

        for msg in messages:
            performance = msg.payload[PayloadKey.PERFORMANCE]
            self._scheduler.record_performance(performance)
            self._logger.info(
                f"ep {self._scheduler.current_ep} - performance: {performance}, "
                f"exploration_params: {self._scheduler.exploration_params}, "
                f"actor_id: {msg.source}"
            )
            self._pending_actor_set.remove(msg.source)

        # If the learner is training,
        if messages[0].payload[PayloadKey.EXPERIENCES]:
            self._agent_manager.train(
                self._experience_collecting_func({msg.source: msg.payload[PayloadKey.EXPERIENCES] for msg in messages})
            )

        self._registry_table.clear()
