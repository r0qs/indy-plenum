from typing import Any, Optional, NamedTuple

from plenum.common.eventually import eventuallyAll, eventually
from plenum.common.log import getlogger
from plenum.common.network_interface import NetworkInterface
from plenum.common.stacked import Stack
from plenum.common.zstack import ZStack
from plenum.common.types import HA
from plenum.test.exceptions import NotFullyConnected
from plenum.common.exceptions import NotConnectedToAny
from plenum.test.stasher import Stasher
from plenum.test.waits import expectedWait
from plenum.common.config_util import getConfig


logger = getlogger()
config = getConfig()


if config.UseZStack:
    BaseStackClass = ZStack
else:
    BaseStackClass = Stack


class TestStack(BaseStackClass):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stasher = Stasher(self.rxMsgs,
                               "TestStack~" + self.name)

        self.delay = self.stasher.delay

    # def _serviceStack(self, age):
    #     super()._serviceStack(age)
    #     self.stasher.process(age)

    async def _serviceStack(self, age):
        await super()._serviceStack(age)
        self.stasher.process(age)

    def resetDelays(self):
        self.stasher.resetDelays()


class StackedTester:
    def checkIfConnectedTo(self, count=None):
        connected = 0
        # TODO refactor to not use values
        for address in self.nodeReg.values():
            for remote in self.nodestack.remotes.values():
                if HA(*remote.ha) == address:
                    if BaseStackClass.isRemoteConnected(remote):
                        connected += 1
                        break
        totalNodes = len(self.nodeReg) if count is None else count
        if count is None and connected == 0:
            raise NotConnectedToAny()
        elif connected < totalNodes:
            raise NotFullyConnected()
        else:
            assert connected == totalNodes

    async def ensureConnectedToNodes(self, timeout=None):
        wait = timeout or expectedWait(len(self.nodeReg))
        logger.debug(
                "waiting for {} seconds to check client connections to "
                "nodes...".format(wait))
        await eventuallyAll(self.checkIfConnectedTo, retryWait=.5,
                            totalTimeout=wait)

    async def ensureDisconnectedToNodes(self, timeout):
        await eventually(self.checkIfConnectedTo, 0, retryWait=.5,
                         timeout=timeout)


def getTestableStack(stack: NetworkInterface):
    """
    Dynamically modify a class that extends from `Stack` and introduce
    `TestStack` in the class hierarchy
    :param stack:
    :return:
    """
    # TODO: Can it be achieved without this mro manipulation?
    mro = stack.__mro__
    newMro = []
    for c in mro[1:]:
        if c == BaseStackClass:
            newMro.append(TestStack)
        newMro.append(c)
    return type(stack.__name__, tuple(newMro), dict(stack.__dict__))


if config.UseZStack:
    RemoteState = NamedTuple("RemoteState", [
        ('isConnected', Optional[bool])
    ])

    CONNECTED = RemoteState(isConnected=True)
    NOT_CONNECTED = RemoteState(isConnected=False)
    # TODO this is to allow imports to pass until we create abstractions for RAET and ZMQ
    JOINED_NOT_ALLOWED = RemoteState(isConnected=False)
    JOINED = RemoteState(isConnected=False)
else:
    RemoteState = NamedTuple("RemoteState", [
        ('joined', Optional[bool]),
        ('allowed', Optional[bool]),
        ('alived', Optional[bool])])

    CONNECTED = RemoteState(joined=True, allowed=True, alived=True)
    NOT_CONNECTED = RemoteState(joined=None, allowed=None, alived=None)
    JOINED_NOT_ALLOWED = RemoteState(joined=True, allowed=None, alived=None)
    JOINED = RemoteState(joined=True, allowed='N/A', alived='N/A')


def checkState(state: RemoteState, obj: Any, details: str=None):
    if state is not None:
        checkedItems = {}
        for key, s in state._asdict().items():
            checkedItems[key] = 'N/A' if s == 'N/A' else getattr(obj, key)
        actualState = RemoteState(**checkedItems)
        assert actualState == state, set(actualState._asdict().items()) - \
                                     set(state._asdict().items())


def checkRemoteExists(frm: Stack,
                      to: str,  # remoteName
                      state: Optional[RemoteState] = None):
    remote = frm.getRemote(to)
    checkState(state, remote, "{}'s remote {}".format(frm.name, to))
