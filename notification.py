import json
import os
import threading
import time
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import Sequence, Optional, Iterable, MutableSequence
from warnings import warn

import jsonpickle


class Urgency(IntEnum):
    LOW = 0
    NORMAL = 1
    CRITICAL = 2


class CloseReason(IntEnum):
    EXPIRED = 1
    DISMISSED = 2
    CLOSED = 3
    RESERVED = 4


class Notification:
    def __init__(self) -> None:
        self.id: Optional[int] = None
        self.deadline: Optional[float] = None
        self.summary: Optional[str] = None
        self.body: Optional[str] = None
        self.application: Optional[str] = None
        self.urgency: int = int(Urgency.NORMAL)
        self.actions: Sequence[str] = []

    def __str__(self) -> str:
        return json.dumps(vars(self))


class NotificationObserver(ABC):
    @abstractmethod
    def activate(self, notification: Notification) -> None:
        pass

    @abstractmethod
    def close(self, nid: int, reason: int) -> None:
        pass


# TODO: make it iterable
class NotificationQueue:
    def __init__(self, queue: MutableSequence[Notification] = None, last_id: int = 1) -> None:
        self._lock: threading.Lock = threading.Lock()
        self.queue: MutableSequence[Notification] = [] if queue is None else queue
        self.last_id: int = last_id
        self.allowed_to_expire: Sequence[str] = []
        self.single_notification_apps: Sequence[str] = ["VLC media player"]
        self.observers: MutableSequence[NotificationObserver] = []

    @property
    def lock(self) -> threading.Lock:
        return self._lock

    def save(self, filename: str) -> None:
        print("Saving notification queue")
        try:
            with open(filename, 'w') as f:
                f.write(jsonpickle.encode(self.queue))
        except:
            warn("Failed to store notification queue")

    def see(self, nid: int) -> None:
        for notification in self.queue:
            if notification.id == nid:
                notification.urgency = int(Urgency.NORMAL)
                for observer in self.observers:
                    observer.activate(notification)
                return
        warn("Unable to find notification {:d}".format(nid))

    def remove(self, nid: int) -> None:
        for notification in self.queue:
            if notification.id == nid:
                print("Removing: {:d}".format(nid))
                self.queue.remove(notification)
                return
        warn("Unable to find notification {:d}".format(nid))

    def remove_all(self, nids: Iterable[int]) -> None:
        to_remove = [n for n in self.queue if n.id in nids]
        for notification in to_remove:
            print("Removing: {:d}".format(notification.id))
            self.queue.remove(notification)

    def put(self, notification: Notification) -> None:
        if notification.application in self.single_notification_apps:
            to_replace = next((n for n in self.queue
                               if n.application == notification.application), None)
        else:
            # cannot have two notifications with the same ID
            to_replace = next((n for n in self.queue if n.id == notification.id), None)
        if to_replace:
            print("Replacing {:d}", to_replace.id)
            self.queue.remove(to_replace)
        else:
            # new notification, increase progressive ID
            notification.id = self.last_id
            self.last_id += 1
        print("Adding: {:d}".format(notification.id))
        self.queue.append(notification)

    def cleanup(self) -> None:
        now = time.time()
        to_remove = [n.id for n in self.queue
                     if n.deadline and n.deadline < now
                     and n.application in self.allowed_to_expire]
        if to_remove:
            print("Expired: {}".format(to_remove))
            self.remove_all(to_remove)
            for observer in self.observers:
                for nid in to_remove:
                    observer.close(nid, CloseReason.EXPIRED)

    @classmethod
    def load(cls, filename: str) -> 'NotificationQueue':
        if not os.path.exists(filename):
            print("Creating empty notification queue")
            return cls([], 1)

        print("Loading notification queue from file")
        with open(filename, 'r') as f:
            queue = jsonpickle.decode(f.read())
        last_id = 1
        for notification in queue:
            if last_id < notification.id:
                last_id = int(notification.id)
        print("Found last id: {:d}".format(last_id))
        return cls(queue, last_id)
