"""HostBase module: Contains the HostBase class"""

from panda3d.core import ExecutionEnvironment, ClockObject, TrueClock, \
    VirtualFileSystem, ConfigPageManager, ConfigVariableManager, Notify, \
    PandaSystem

from .DirectObject import DirectObject
from direct.directnotify.DirectNotifyGlobal import directNotify, giveNotify
from . import DConfig
from .EventManagerGlobal import eventMgr
from .MessengerGlobal import messenger
from .BulletinBoardGlobal import bulletinBoard
from .Loader import Loader
from direct.task.TaskManagerGlobal import taskMgr, simTaskMgr
from direct.task import Task
from .JobManagerGlobal import jobMgr
from . import ExceptionVarDump

# Register the extension methods for NodePath.
from direct.extensions_native import NodePath_extensions

# This needs to be available early for DirectGUI imports
import sys
import builtins
builtins.config = DConfig

class HostBase(DirectObject):
    """
    Base class for any DIRECT-based application that needs to run simulation
    frames and capture events.
    """

    #: The deprecated `.DConfig` interface for accessing config variables.
    config = DConfig
    notify = directNotify.newCategory("HostBase")

    def __init__(self):
        #: The directory containing the main Python file of this application.
        self.mainDir = ExecutionEnvironment.getEnvironmentVariable("MAIN_DIR")
        self.main_dir = self.mainDir

        self.wantStats = self.config.GetBool('want-pstats', 0)

        # Do you want to enable a fixed simulation timestep?  Setting this true
        # only means that the builtin resetPrevTransform and collisionLoop
        # tasks are added onto the simTaskMgr instead of taskMgr, which runs at
        # a fixed time step.  You can still add your own fixed timestep tasks
        # when this is false, it only has to do with builtin simulation tasks.
        self.fixedSimulationStep = self.config.GetBool('want-fixed-simulation-step', 0)

        #: The global event manager, as imported from `.EventManagerGlobal`.
        self.eventMgr = eventMgr
        #: The global messenger, as imported from `.MessengerGlobal`.
        self.messenger = messenger
        #: The global bulletin board, as imported from `.BulletinBoardGlobal`.
        self.bboard = bulletinBoard
        #: The global task manager, as imported from `.TaskManagerGlobal`.
        self.taskMgr = taskMgr
        self.task_mgr = taskMgr
        #: The global simulation task manager, as imported from `.TaskManagerGlobal`
        self.simTaskMgr = simTaskMgr
        self.sim_task_mgr = simTaskMgr
        #: The global job manager, as imported from `.JobManagerGlobal`.
        self.jobMgr = jobMgr

        #: `.Loader.Loader` object.
        self.loader = Loader(self)

        # Get a pointer to Panda's global ClockObject, used for
        # synchronizing events between Python and C.
        globalClock = ClockObject.getGlobalClock()
        # We will manually manage the clock
        globalClock.setMode(ClockObject.MSlave)
        self.globalClock = globalClock

        # Since we have already started up a TaskManager, and probably
        # a number of tasks; and since the TaskManager had to use the
        # TrueClock to tell time until this moment, make sure the
        # globalClock object is exactly in sync with the TrueClock.
        trueClock = TrueClock.getGlobalPtr()
        self.trueClock = trueClock
        globalClock.setRealTime(trueClock.getShortTime())
        globalClock.tick()

        # Now we can make the TaskManager start using the new globalClock.
        taskMgr.globalClock = globalClock
        simTaskMgr.globalClock = globalClock

        vfs = VirtualFileSystem.getGlobalPtr()
        self.vfs = vfs

        # Make sure we're not making more than one HostBase.
        if hasattr(builtins, 'base'):
            raise Exception("Attempt to spawn multiple HostBase instances!")

        # DO NOT ADD TO THIS LIST.  We're trying to phase out the use of
        # built-in variables by ShowBase.  Use a Global module if necessary.
        builtins.base = self
        builtins.taskMgr = self.taskMgr
        builtins.simTaskMgr = self.simTaskMgr
        builtins.jobMgr = self.jobMgr
        builtins.eventMgr = self.eventMgr
        builtins.messenger = self.messenger
        builtins.bboard = self.bboard
        builtins.loader = self.loader
        # Config needs to be defined before ShowBase is constructed
        #builtins.config = self.config
        builtins.ostream = Notify.out()
        builtins.directNotify = directNotify
        builtins.giveNotify = giveNotify
        builtins.globalClock = globalClock
        builtins.vfs = vfs
        builtins.cpMgr = ConfigPageManager.getGlobalPtr()
        builtins.cvMgr = ConfigVariableManager.getGlobalPtr()
        builtins.pandaSystem = PandaSystem.getGlobalPtr()

        # Now add this instance to the ShowBaseGlobal module scope.
        from . import ShowBaseGlobal
        builtins.run = ShowBaseGlobal.run
        ShowBaseGlobal.base = self

        # What is the current frame number?
        self.frameCount = 0
        # Time at beginning of current frame
        self.frameTime = self.globalClock.getRealTime()
        # How long did the last frame take.
        self.deltaTime = 0

        #
        # Variables pertaining to simulation ticks.
        #

        self.prevRemainder = 0
        self.remainder = 0
        # What is the current overall simulation tick?
        self.tickCount = 0
        # How many ticks are we going to run this frame?
        self.totalTicksThisFrame = 0
        # How many ticks have we run so far this frame?
        self.currentTicksThisFrame = 0
        # What tick are we currently on this frame?
        self.currentFrameTick = 0
        # How many simulations ticks are we running per-second?
        self.ticksPerSec = 60
        self.intervalPerTick = 1.0 / self.ticksPerSec

        self.taskMgr.finalInit()

    def shutdown(self):
        self.eventMgr.shutdown()

    def destroy(self):
        """ Call this function to destroy the HostBase and stop all
        its tasks, freeing all of the Panda resources.  Normally, you
        should not need to call it explicitly, as it is bound to the
        exitfunc and will be called at application exit time
        automatically.

        This function is designed to be safe to call multiple times."""

        # Remove the built-in base reference
        if getattr(builtins, 'base', None) is self:
            del builtins.run
            del builtins.base
            del builtins.loader
            del builtins.taskMgr
            del builtins.simTaskMgr
            ShowBaseGlobal = sys.modules.get('direct.showbase.ShowBaseGlobal', None)
            if ShowBaseGlobal:
                del ShowBaseGlobal.base

        self.ignoreAll()
        self.shutdown()

        if getattr(self, 'loader', None):
            self.loader.destroy()
            self.loader = None

    def setTickRate(self, rate):
        """Sets the number of simulation steps that should run each second."""
        self.ticksPerSec = rate
        self.intervalPerTick = 1.0 / self.ticksPerSec

    def ticksToTime(self, ticks):
        """Returns the frame time of a tick number."""
        return self.intervalPerTick * float(ticks)

    def timeToTicks(self, time):
        """Returns the tick number for a frame time."""
        return int(0.5 + float(time) / self.intervalPerTick)

    def isFinalTick(self):
        """
        Returns true if we are currently on the final simulation tick of
        this frame.
        """
        return self.currentTicksThisFrame == self.totalTicksThisFrame

    def preRunFrame(self):
        pass

    def runFrame(self):
        #
        # First determine how many simulation ticks we should run.
        #

        self.prevRemainder = self.remainder
        if self.prevRemainder < 0.0:
            self.prevRemainder = 0.0

        self.remainder += self.deltaTime

        numTicks = 0
        if self.remainder >= self.intervalPerTick:
            numTicks = int(self.remainder / self.intervalPerTick)
            self.remainder -= numTicks * self.intervalPerTick

        self.totalTicksThisFrame = numTicks
        self.currentFrameTick = 0
        self.currentTicksThisFrame = 1

        realDeltaTime = self.deltaTime

        #
        # Now run any simulation ticks.
        #

        for _ in range(numTicks):
            # Determine delta and frame time of this sim tick
            frameTime = self.intervalPerTick * self.tickCount
            deltaTime = self.intervalPerTick
            self.deltaTime = deltaTime
            self.frameTime = frameTime
            # Set it on the global clock for anything that uses it
            self.globalClock.setFrameTime(frameTime)
            self.globalClock.setDt(deltaTime)
            self.globalClock.setFrameCount(self.tickCount)

            # Step all simulation-bound tasks
            self.simTaskMgr.step()

            self.tickCount += 1
            self.currentFrameTick += 1
            self.currentTicksThisFrame += 1

        # Restore the true time for rendering and frame-bound stuff
        frameTime = self.tickCount * self.intervalPerTick + self.remainder
        self.globalClock.setFrameTime(frameTime)
        self.globalClock.setDt(realDeltaTime)
        self.globalClock.setFrameCount(self.frameCount)
        self.deltaTime = realDeltaTime
        self.frameTime = frameTime

        # And finally, step all frame-bound tasks
        self.taskMgr.step()

    def postRunFrame(self):
        pass

    def doRunFrame(self):
        # Manually advance the clock
        now = self.globalClock.getRealTime()
        self.deltaTime = now - self.frameTime
        self.frameTime = now

        self.globalClock.setFrameTime(self.frameTime)
        self.globalClock.setDt(self.deltaTime)
        self.globalClock.setFrameCount(self.frameCount)

        self.preRunFrame()
        self.runFrame()
        self.postRunFrame()

        self.frameCount += 1

    def run(self):
        """Starts the main loop of the application."""

        if PandaSystem.getPlatform() == 'emscripten':
            return

        # Set the clock to have last frame's time in case we were
        # Paused at the prompt for a long time
        t = self.globalClock.getFrameTime()
        timeDelta = t - self.globalClock.getRealTime()
        self.globalClock.setRealTime(t)
        self.messenger.send("resetClock", [timeDelta])

        if self.taskMgr.resumeFunc != None:
            self.taskMgr.resumeFunc()

        if self.taskMgr.stepping:
            self.doRunFrame()
        else:
            self.taskMgr.running = True
            while self.taskMgr.running:
                try:
                    self.doRunFrame()
                except KeyboardInterrupt:
                    self.taskMgr.stop()
                except SystemError:
                    self.taskMgr.stop()
                    raise
                except IOError as ioError:
                    code, _ = self.taskMgr.unpackIOError(ioError)
                    # Since upgrading to Python 2.4.1, pausing the execution
                    # often gives this IOError during the sleep function:
                    #     IOError: [Errno 4] Interrupted function call
                    # So, let's just handle that specific exception and stop.
                    # All other IOErrors should still get raised.
                    # Only problem: legit IOError 4s will be obfuscated.
                    if code == 4:
                        self.taskMgr.stop()
                    else:
                        raise
                except Exception as e:
                    if self.taskMgr.extendedExceptions:
                        self.taskMgr.stop()
                        Task.print_exc_plus()
                    else:
                        if (ExceptionVarDump.wantStackDumpLog and
                            ExceptionVarDump.dumpOnExceptionInit):
                            ExceptionVarDump._varDump__print(e)
                        raise
                except:
                    if self.taskMgr.extendedExceptions:
                        self.taskMgr.stop()
                        Task.print_exc_plus()
                    else:
                        raise

        self.taskMgr.mgr.stopThreads()
