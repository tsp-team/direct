"""Actor module: contains the Actor class"""

__all__ = ['Actor']

from pandac.PandaModules import *
from direct.showbase.DirectObject import DirectObject
from pandac.PandaModules import LODNode
import types, copy

class Actor(DirectObject, NodePath):
    """
    Actor class: Contains methods for creating, manipulating
    and playing animations on characters
    """
    notify = directNotify.newCategory("Actor")
    partPrefix = "__Actor_"

    modelLoaderOptions = LoaderOptions(LoaderOptions.LFSearch |
                                       LoaderOptions.LFReportErrors |
                                       LoaderOptions.LFConvertSkeleton)
    animLoaderOptions =  LoaderOptions(LoaderOptions.LFSearch |
                                       LoaderOptions.LFReportErrors |
                                       LoaderOptions.LFConvertAnim)

    class PartDef:

        """Instances of this class are stored within the
        PartBundleDict to track all of the individual PartBundles
        associated with the Actor.  In general, each separately loaded
        model file is a different PartBundle.  This can include the
        multiple different LOD's, as well as the multiple different
        pieces of a multipart Actor. """
        
        def __init__(self, partBundleNP, partBundle, partModel):
            # We also save the ModelRoot node along with the
            # PartBundle, so that the reference count in the ModelPool
            # will be accurate.
            self.partBundleNP = partBundleNP
            self.partBundle = partBundle
            self.partModel = partModel
        
        def __repr__(self):
            return 'Actor.PartDef(%s, %s)' % (repr(self.partBundleNP), repr(self.partModel))

    class AnimDef:

        """Instances of this class are stored within the
        AnimControlDict to track all of the animations associated with
        the Actor.  This includes animations that have already been
        bound (these have a valid AnimControl) as well as those that
        have not yet been bound (for these, self.animControl is None).

        There is a different AnimDef for each different part or
        sub-part, times each different animation in the AnimDict. """
        
        def __init__(self, filename):
            self.filename = filename
            self.animModel = None
            self.animControl = None

        def makeCopy(self):
            return Actor.AnimDef(self.filename)

        def __repr__(self):
            return 'Actor.AnimDef(%s)' % (repr(self.filename))

    class SubpartDef:

        """Instances of this class are stored within the SubpartDict
        to track the existance of arbitrary sub-parts.  These are
        designed to appear to the user to be identical to true "part"
        of a multi-part Actor, but in fact each subpart represents a
        subset of the joints of an existing part (which is accessible
        via a different name). """

        def __init__(self, truePartName, subset = PartSubset()):
            self.truePartName = truePartName
            self.subset = subset

        def makeCopy(self):
            return Actor.SubpartDef(self.truePartName, PartSubset(self.subset))
            
        
        def __repr__(self):
            return 'Actor.SubpartDef(%s, %s)' % (repr(self.truePartName), repr(self.subset))

    def __init__(self, models=None, anims=None, other=None, copy=1,
                 lodNode = None, flattenable = 1, setFinal = 0):
        """__init__(self, string | string:string{}, string:string{} |
        string:(string:string{}){}, Actor=None)
        Actor constructor: can be used to create single or multipart
        actors. If another Actor is supplied as an argument this
        method acts like a copy constructor. Single part actors are
        created by calling with a model and animation dictionary
        (animName:animPath{}) as follows:

           a = Actor("panda-3k.egg", {"walk":"panda-walk.egg" \
                                      "run":"panda-run.egg"})

        This could be displayed and animated as such:

           a.reparentTo(render)
           a.loop("walk")
           a.stop()

        Multipart actors expect a dictionary of parts and a dictionary
        of animation dictionaries (partName:(animName:animPath{}){}) as
        below:

            a = Actor(

                # part dictionary
                {"head":"char/dogMM/dogMM_Shorts-head-mod", \
                 "torso":"char/dogMM/dogMM_Shorts-torso-mod", \
                 "legs":"char/dogMM/dogMM_Shorts-legs-mod"}, \

                # dictionary of anim dictionaries
                {"head":{"walk":"char/dogMM/dogMM_Shorts-head-walk", \
                         "run":"char/dogMM/dogMM_Shorts-head-run"}, \
                 "torso":{"walk":"char/dogMM/dogMM_Shorts-torso-walk", \
                          "run":"char/dogMM/dogMM_Shorts-torso-run"}, \
                 "legs":{"walk":"char/dogMM/dogMM_Shorts-legs-walk", \
                         "run":"char/dogMM/dogMM_Shorts-legs-run"} \
                 })

        In addition multipart actor parts need to be connected together
        in a meaningful fashion:

            a.attach("head", "torso", "joint-head")
            a.attach("torso", "legs", "joint-hips")

        #
        # ADD LOD COMMENT HERE!
        #

        Other useful Actor class functions:

            #fix actor eye rendering
            a.drawInFront("joint-pupil?", "eyes*")

            #fix bounding volumes - this must be done after drawing
            #the actor for a few frames, otherwise it has no effect
            a.fixBounds()
        """
        try:
            self.Actor_initialized
            return
        except:
            self.Actor_initialized = 1

        # initialize our NodePath essence
        NodePath.__init__(self)

        self.__autoCopy = copy

        # create data structures
        self.__partBundleDict = {}
        self.__subpartDict = {}
        self.__sortedLODNames = []
        self.__animControlDict = {}
        self.__controlJoints = {}
        self.__frozenJoints = {}        

        self.__subpartsComplete = False

        self.__LODNode = None
        self.switches = None

        if (other == None):
            # act like a normal constructor

            # create base hierarchy
            self.gotName = 0

            if flattenable:
                # If we want a flattenable Actor, don't create all
                # those ModelNodes, and the GeomNode is the same as
                # the root.
                root = PandaNode('actor')
                self.assign(NodePath(root))
                self.setGeomNode(NodePath(self))

            else:
                # A standard Actor has a ModelNode at the root, and
                # another ModelNode to protect the GeomNode.
                root = ModelNode('actor')
                root.setPreserveTransform(1)
                self.assign(NodePath(root))
                self.setGeomNode(self.attachNewNode(ModelNode('actorGeom')))
                
            self.__hasLOD = 0

            # load models
            #
            # four cases:
            #
            #   models, anims{} = single part actor
            #   models{}, anims{} =  single part actor w/ LOD
            #   models{}, anims{}{} = multi-part actor
            #   models{}{}, anims{}{} = multi-part actor w/ LOD
            #
            # make sure we have models
            if (models):
                # do we have a dictionary of models?
                if (type(models)==type({})):
                    # if this is a dictionary of dictionaries
                    if (type(models[models.keys()[0]]) == type({})):
                        # then it must be a multipart actor w/LOD
                        self.setLODNode(node = lodNode)
                        # preserve numerical order for lod's
                        # this will make it easier to set ranges
                        sortedKeys = models.keys()
                        sortedKeys.sort()
                        for lodName in sortedKeys:
                            # make a node under the LOD switch
                            # for each lod (just because!)
                            self.addLOD(str(lodName))
                            # iterate over both dicts
                            for modelName in models[lodName].keys():
                                self.loadModel(models[lodName][modelName],
                                               modelName, lodName, copy = copy)
                    # then if there is a dictionary of dictionaries of anims
                    elif (type(anims[anims.keys()[0]])==type({})):
                        # then this is a multipart actor w/o LOD
                        for partName in models.keys():
                            # pass in each part
                            self.loadModel(models[partName], partName, copy = copy)
                    else:
                        # it is a single part actor w/LOD
                        self.setLODNode(node = lodNode)
                        # preserve order of LOD's
                        sortedKeys = models.keys()
                        sortedKeys.sort()
                        for lodName in sortedKeys:
                            self.addLOD(str(lodName))
                            # pass in dictionary of parts
                            self.loadModel(models[lodName], lodName=lodName, copy = copy)
                else:
                    # else it is a single part actor
                    self.loadModel(models, copy = copy)

            # load anims
            # make sure the actor has animations
            if (anims):
                if (len(anims) >= 1):
                    # if so, does it have a dictionary of dictionaries?
                    if (type(anims[anims.keys()[0]])==type({})):
                        # are the models a dict of dicts too?
                        if (type(models)==type({})):
                            if (type(models[models.keys()[0]]) == type({})):
                                # then we have a multi-part w/ LOD
                                sortedKeys = models.keys()
                                sortedKeys.sort()
                                for lodName in sortedKeys:
                                    # iterate over both dicts
                                    for partName in anims.keys():
                                        self.loadAnims(
                                            anims[partName], partName, lodName)
                            else:
                                # then it must be multi-part w/o LOD
                                for partName in anims.keys():
                                    self.loadAnims(anims[partName], partName)
                    elif (type(models)==type({})):
                        # then we have single-part w/ LOD
                        sortedKeys = models.keys()
                        sortedKeys.sort()
                        for lodName in sortedKeys:
                            self.loadAnims(anims, lodName=lodName)
                    else:
                        # else it is single-part w/o LOD
                        self.loadAnims(anims)

        else:
            self.copyActor(other, True) # overwrite everything

        if setFinal:
            # If setFinal is true, the Actor will set its top bounding
            # volume to be the "final" bounding volume: the bounding
            # volumes below the top volume will not be tested.  If a
            # cull test passes the top bounding volume, the whole
            # Actor is rendered.

            # We do this partly because an Actor is likely to be a
            # fairly small object relative to the scene, and is pretty
            # much going to be all onscreen or all offscreen anyway;
            # and partly because of the Character bug that doesn't
            # update the bounding volume for pieces that animate away
            # from their original position.  It's disturbing to see
            # someone's hands disappear; better to cull the whole
            # object or none of it.
            self.__geomNode.node().setFinal(1)

    def delete(self):
        try:
            self.Actor_deleted
            return
        except:
            self.Actor_deleted = 1
            self.cleanup()

    def copyActor(self, other, overwrite=False):
            # act like a copy constructor
            self.gotName = other.gotName
            
            # copy the scene graph elements of other
            if (overwrite):
                otherCopy = other.copyTo(NodePath())
                otherCopy.detachNode()
                # assign these elements to ourselve (overwrite)
                self.assign(otherCopy)
            else:
                # just copy these to ourselve
                otherCopy = other.copyTo(self)
            self.setGeomNode(otherCopy.getChild(0))

            # copy the switches for lods
            self.switches = other.switches
            self.__LODNode = self.find('**/+LODNode')
            self.__hasLOD = 0
            if (not self.__LODNode.isEmpty()):
                self.__hasLOD = 1


            # copy the part dictionary from other
            self.__copyPartBundles(other)
            self.__copySubpartDict(other)
            self.__subpartsComplete = other.__subpartsComplete
            
            # copy the anim dictionary from other
            self.__copyAnimControls(other)


    def __cmp__(self, other):
        # Actor inherits from NodePath, which inherits a definition of
        # __cmp__ from FFIExternalObject that uses the NodePath's
        # compareTo() method to compare different NodePaths.  But we
        # don't want this behavior for Actors; Actors should only be
        # compared pointerwise.  A NodePath that happens to reference
        # the same node is still different from the Actor.
        if self is other:
            return 0
        else:
            return 1

    def __str__(self):
        """
        Actor print function
        """
        return "Actor %s, parts = %s, LODs = %s, anims = %s" % \
               (self.getName(), self.getPartNames(), self.getLODNames(), self.getAnimNames())

    def listJoints(self, partName="modelRoot", lodName="lodRoot"):
        """Handy utility function to list the joint hierarchy of the
        actor. """

        partBundleDict = self.__partBundleDict.get(lodName)
        if not partBundleDict:
            Actor.notify.error("no lod named: %s" % (lodName))

        subpartDef = self.__subpartDict.get(partName, Actor.SubpartDef(partName))

        partDef = partBundleDict.get(subpartDef.truePartName)
        if partDef == None:
            Actor.notify.error("no part named: %s" % (partName))

        self.__doListJoints(0, partDef.partBundle,
                            subpartDef.subset.isIncludeEmpty(), subpartDef.subset)

    def __doListJoints(self, indentLevel, part, isIncluded, subset):
        name = part.getName()
        if subset.matchesInclude(name):
            isIncluded = True
        elif subset.matchesExclude(name):
            isIncluded = False

        if isIncluded:
            value = ''
            if hasattr(part, 'outputValue'):
                lineStream = LineStream.LineStream()
                part.outputValue(lineStream)
                value = lineStream.getLine()

            print ' ' * indentLevel, part.getName(), value

        for i in range(part.getNumChildren()):
            self.__doListJoints(indentLevel + 2, part.getChild(i),
                                isIncluded, subset)


    def getActorInfo(self):
        """
        Utility function to create a list of information about an actor.
        Useful for iterating over details of an actor.
        """
        lodInfo = []
        for lodName in self.__animControlDict.keys():
            partDict = self.__animControlDict[lodName]
            partInfo = []
            for partName in partDict.keys():
                subpartDef = self.__subpartDict.get(partName, Actor.SubpartDef(partName))
                partBundleDict = self.__partBundleDict.get(lodName)
                partDef = partBundleDict.get(subpartDef.truePartName)
                partBundle = partDef.partBundle
                animDict = partDict[partName]
                animInfo = []
                for animName in animDict.keys():
                    file = animDict[animName].filename
                    animControl = animDict[animName].animControl
                    animInfo.append([animName, file, animControl])
                partInfo.append([partName, partBundle, animInfo])
            lodInfo.append([lodName, partInfo])
        return lodInfo

    def getAnimNames(self):
        animNames = []
        for lodName, lodInfo in self.getActorInfo():
            for partName, bundle, animInfo in lodInfo:
                for animName, file, animControl in animInfo:
                    if animName not in animNames:
                        animNames.append(animName)
        return animNames

    def pprint(self):
        """
        Pretty print actor's details
        """
        for lodName, lodInfo in self.getActorInfo():
            print 'LOD:', lodName
            for partName, bundle, animInfo in lodInfo:
                print '  Part:', partName
                print '  Bundle:', `bundle`
                for animName, file, animControl in animInfo:
                    print '    Anim:', animName
                    print '      File:', file
                    if animControl == None:
                        print ' (not loaded)'
                    else:
                        print ('      NumFrames: %d PlayRate: %0.2f' %
                               (animControl.getNumFrames(),
                                animControl.getPlayRate()))

    def cleanup(self):
        """
        Actor cleanup function
        """
        self.stop(None)
        self.__frozenJoints = {}
        self.flush()
        if(self.__geomNode):
            self.__geomNode.removeNode()
            self.__geomNode = None
        if not self.isEmpty():
            self.removeNode()

    def removeNode(self):
        if self.__geomNode and (self.__geomNode.getNumChildren() > 0):
            self.notify.warning("called actor.removeNode() on %s without calling cleanup()" % self.getName())
        NodePath.removeNode(self)

    def clearPythonData(self):
        self.__partBundleDict = {}
        self.__subpartDict = {}
        self.__sortedLODNames = []
        self.__animControlDict = {}
        self.__controlJoints = {}
        
    def flush(self):
        """
        Actor flush function
        """
        self.clearPythonData()

        if self.__LODNode and (not self.__LODNode.isEmpty()):
            self.__LODNode.removeNode()
            self.__LODNode = None

        # remove all its children
        if(self.__geomNode):
            self.__geomNode.removeChildren()

        
        self.__hasLOD = 0

    # accessing

    def getAnimControlDict(self):
        return self.__animControlDict

    def removeAnimControlDict(self):
        self.__animControlDict = {}

    def getPartBundleDict(self):
        return self.__partBundleDict

    def __updateSortedLODNames(self):
        # Cache the sorted LOD names so we dont have to grab them
        # and sort them every time somebody asks for the list
        self.__sortedLODNames = self.__partBundleDict.keys()
        # Reverse sort the doing a string->int
        def sortFunc(x, y):
            if not str(x).isdigit():
                smap = {'h':3,
                        'm':2,
                        'l':1,
                        'f':0}

                """
                sx = smap.get(x[0],None)
                sy = smap.get(y[0],None)

                if sx is None:
                    self.notify.error('Invalid lodName: %s' % x)
                if sy is None:
                    self.notify.error('Invalid lodName: %s' % y)
                """
                return cmp(smap[y[0]], smap[x[0]])
            else:
                return cmp (int(y), int(x))

        self.__sortedLODNames.sort(sortFunc)

    def getLODNames(self):
        """
        Return list of Actor LOD names. If not an LOD actor,
        returns 'lodRoot'
        Caution - this returns a reference to the list - not your own copy
        """
        return self.__sortedLODNames

    def getPartNames(self):
        """
        Return list of Actor part names. If not an multipart actor,
        returns 'modelRoot' NOTE: returns parts of arbitrary LOD
        """
        partNames = []
        if self.__partBundleDict:
            partNames = self.__partBundleDict.values()[0].keys()
        return partNames + self.__subpartDict.keys()

    def getGeomNode(self):
        """
        Return the node that contains all actor geometry
        """
        return self.__geomNode

    def setGeomNode(self, node):
        """
        Set the node that contains all actor geometry
        """
        self.__geomNode = node

    def getLODNode(self):
        """
        Return the node that switches actor geometry in and out"""
        return self.__LODNode.node()

    def setLODNode(self, node=None):
        """
        Set the node that switches actor geometry in and out.
        If one is not supplied as an argument, make one
        """
        if (node == None):
            node = LODNode.makeDefaultLod("lod")

        if self.__LODNode:
            self.__LODNode = node
        else:
            self.__LODNode = self.__geomNode.attachNewNode(node)
            self.__hasLOD = 1
            self.switches = {}
        

    def useLOD(self, lodName):
        """
        Make the Actor ONLY display the given LOD
        """
        # make sure we don't call this twice in a row
        # and pollute the the switches dictionary
        sortedKeys = self.switches.keys()
        sortedKeys.sort()
        index = sortedKeys.index(lodName)
        self.__LODNode.node().forceSwitch(index)

    def printLOD(self):
        sortedKeys = self.switches.keys()
        sortedKeys.sort()
        for eachLod in sortedKeys:
            print "python switches for %s: in: %d, out %d" % (eachLod,
                                              self.switches[eachLod][0],
                                              self.switches[eachLod][1])

        switchNum = self.__LODNode.node().getNumSwitches()
        for eachSwitch in range(0, switchNum):
            print "c++ switches for %d: in: %d, out: %d" % (eachSwitch,
                   self.__LODNode.node().getIn(eachSwitch),
                   self.__LODNode.node().getOut(eachSwitch))


    def resetLOD(self):
        """
        Restore all switch distance info (usually after a useLOD call)"""
        self.__LODNode.node().clearForceSwitch()
##         sortedKeys = self.switches.keys()
##         sortedKeys.sort()
##         for eachLod in sortedKeys:
##             index = sortedKeys.index(eachLod)
##             self.__LODNode.node().setSwitch(index, self.switches[eachLod][0],
##                                      self.switches[eachLod][1])

    def addLOD(self, lodName, inDist=0, outDist=0, center=None):
        """addLOD(self, string)
        Add a named node under the LODNode to parent all geometry
        of a specific LOD under.
        """
        self.__LODNode.attachNewNode(str(lodName))
        # save the switch distance info
        self.switches[lodName] = [inDist, outDist]
        # add the switch distance info
        self.__LODNode.node().addSwitch(inDist, outDist)
        if center != None:
            self.__LODNode.node().setCenter(center)

    def setLOD(self, lodName, inDist=0, outDist=0):
        """setLOD(self, string)
        Set the switch distance for given LOD
        """
        # save the switch distance info
        self.switches[lodName] = [inDist, outDist]
        # add the switch distance info
        sortedKeys = self.switches.keys()
        sortedKeys.sort()
        index = sortedKeys.index(lodName)
        self.__LODNode.node().setSwitch(index, inDist, outDist)

    def getLOD(self, lodName):
        """getLOD(self, string)
        Get the named node under the LOD to which we parent all LOD
        specific geometry to. Returns 'None' if not found
        """
        if self.__LODNode:
            lod = self.__LODNode.find("**/%s"%lodName)
            if lod.isEmpty():
                return None
            else:
                return lod
        else:
            return None

    def hasLOD(self):
        """
        Return 1 if the actor has LODs, 0 otherwise
        """
        return self.__hasLOD

    def setCenter(self, center):
        if center != None:
            self.__LODNode.node().setCenter(center)

    def update(self, lod=0, partName=None, lodName=None, force=False):
        """ Updates all of the Actor's joints in the indicated LOD.
        The LOD may be specified by name, or by number, where 0 is the
        highest level of detail, 1 is the next highest, and so on.

        If force is True, this will update every joint, even if we
        don't believe it's necessary.
        
        Returns True if any joint has changed as a result of this,
        False otherwise. """

        if lodName == None:
            lodNames = self.getLODNames()
        else:
            lodNames = [lodName]

        anyChanged = False
        if lod < len(lodNames):
            lodName = lodNames[lod]
            if partName == None:
                partBundleDict = self.__partBundleDict[lodName]
                partNames = partBundleDict.keys()
            else:
                partNames = [partName]

            for partName in partNames:
                partBundle = self.getPartBundle(partName, lodNames[lod])
                if force:
                    if partBundle.forceUpdate():
                        anyChanged = True
                else:
                    if partBundle.update():
                        anyChanged = True
        else:
            self.notify.warning('update() - no lod: %d' % lod)

        return anyChanged

    def getFrameRate(self, animName=None, partName=None):
        """getFrameRate(self, string, string=None)
        Return actual frame rate of given anim name and given part.
        If no anim specified, use the currently playing anim.
        If no part specified, return anim durations of first part.
        NOTE: returns info only for an arbitrary LOD
        """
        lodName = self.__animControlDict.keys()[0]
        controls = self.getAnimControls(animName, partName)
        if len(controls) == 0:
            return None

        return controls[0].getFrameRate()

    def getBaseFrameRate(self, animName=None, partName=None):
        """getBaseFrameRate(self, string, string=None)
        Return frame rate of given anim name and given part, unmodified
        by any play rate in effect.
        """
        lodName = self.__animControlDict.keys()[0]
        controls = self.getAnimControls(animName, partName)
        if len(controls) == 0:
            return None

        return controls[0].getAnim().getBaseFrameRate()

    def getPlayRate(self, animName=None, partName=None):
        """
        Return the play rate of given anim for a given part.
        If no part is given, assume first part in dictionary.
        If no anim is given, find the current anim for the part.
        NOTE: Returns info only for an arbitrary LOD
        """
        # use the first lod
        lodName = self.__animControlDict.keys()[0]
        controls = self.getAnimControls(animName, partName)
        if len(controls) == 0:
            return None

        return controls[0].getPlayRate()

    def setPlayRate(self, rate, animName, partName=None):
        """setPlayRate(self, float, string, string=None)
        Set the play rate of given anim for a given part.
        If no part is given, set for all parts in dictionary.

        It used to be legal to let the animName default to the
        currently-playing anim, but this was confusing and could lead
        to the wrong anim's play rate getting set.  Better to insist
        on this parameter.
        NOTE: sets play rate on all LODs"""
        for control in self.getAnimControls(animName, partName):
            control.setPlayRate(rate)

    def getDuration(self, animName=None, partName=None,
                    fromFrame=None, toFrame=None):
        """
        Return duration of given anim name and given part.
        If no anim specified, use the currently playing anim.
        If no part specified, return anim duration of first part.
        NOTE: returns info for arbitrary LOD
        """
        lodName = self.__animControlDict.keys()[0]
        controls = self.getAnimControls(animName, partName)
        if len(controls) == 0:
            return None

        animControl = controls[0]
        if fromFrame is None:
            fromFrame = 0
        if toFrame is None:
            toFrame = animControl.getNumFrames()-1
        return ((toFrame+1)-fromFrame) / animControl.getFrameRate()

    def getNumFrames(self, animName=None, partName=None):
        lodName = self.__animControlDict.keys()[0]
        controls = self.getAnimControls(animName, partName)
        if len(controls) == 0:
            return None
        return controls[0].getNumFrames()

    def getFrameTime(self, anim, frame, partName=None):
        numFrames = self.getNumFrames(anim,partName)
        animTime = self.getDuration(anim,partName)
        frameTime = animTime * float(frame) / numFrames
        return frameTime

    def getCurrentAnim(self, partName=None):
        """
        Return the anim currently playing on the actor. If part not
        specified return current anim of an arbitrary part in dictionary.
        NOTE: only returns info for an arbitrary LOD
        """
        lodName, animControlDict = self.__animControlDict.items()[0]
        if partName == None:
            partName, animDict = animControlDict.items()[0]
        else:
            animDict = animControlDict.get(partName)
            if animDict == None:
                # part was not present
                Actor.notify.warning("couldn't find part: %s" % (partName))
                return None

        # loop through all anims for named part and find if any are playing
        for animName, anim in animDict.items():
            if isinstance(anim.animControl, AnimControl) and anim.animControl.isPlaying():
                return animName

        # we must have found none, or gotten an error
        return None

    def getCurrentFrame(self, animName=None, partName=None):
        """
        Return the current frame number of the anim current playing on
        the actor. If part not specified return current anim of first
        part in dictionary.
        NOTE: only returns info for an arbitrary LOD
        """
        lodName, animControlDict = self.__animControlDict.items()[0]
        if partName == None:
            partName, animDict = animControlDict.items()[0]
        else:
            animDict = animControlDict.get(partName)
            if animDict == None:
                # part was not present
                Actor.notify.warning("couldn't find part: %s" % (partName))
                return None

        # loop through all anims for named part and find if any are playing
        for animName, anim in animDict.items():
            if isinstance(anim.animControl, AnimControl) and anim.animControl.isPlaying():
                return anim.animControl.getFrame()

        # we must have found none, or gotten an error
        return None


    # arranging

    def getPart(self, partName, lodName="lodRoot"):
        """
        Find the named part in the optional named lod and return it, or
        return None if not present
        """
        partBundleDict = self.__partBundleDict.get(lodName)
        if not partBundleDict:
            Actor.notify.warning("no lod named: %s" % (lodName))
            return None
        subpartDef = self.__subpartDict.get(partName, Actor.SubpartDef(partName))
        partDef = partBundleDict.get(subpartDef.truePartName)
        if partDef != None:
            return partDef.partBundleNP
        return None

    def getPartBundle(self, partName, lodName="lodRoot"):
        """
        Find the named part in the optional named lod and return its
        associated PartBundle, or return None if not present
        """
        partBundleDict = self.__partBundleDict.get(lodName)
        if not partBundleDict:
            Actor.notify.warning("no lod named: %s" % (lodName))
            return None
        subpartDef = self.__subpartDict.get(partName, Actor.SubpartDef(partName))
        partDef = partBundleDict.get(subpartDef.truePartName)
        if partDef != None:
            return partDef.partBundle
        return None

    def removePart(self, partName, lodName="lodRoot"):
        """
        Remove the geometry and animations of the named part of the
        optional named lod if present.
        NOTE: this will remove child geometry also!
        """
        # find the corresponding part bundle dict
        partBundleDict = self.__partBundleDict.get(lodName)
        if not partBundleDict:
            Actor.notify.warning("no lod named: %s" % (lodName))
            return

        # remove the part
        if (partBundleDict.has_key(partName)):
            partBundleDict[partName].partBundleNP.removeNode()
            del(partBundleDict[partName])

        # find the corresponding anim control dict
        partDict = self.__animControlDict.get(lodName)
        if not partDict:
            Actor.notify.warning("no lod named: %s" % (lodName))
            return

        # remove the animations
        if (partDict.has_key(partName)):
            del(partDict[partName])

    def hidePart(self, partName, lodName="lodRoot"):
        """
        Make the given part of the optionally given lod not render,
        even though still in the tree.
        NOTE: this will affect child geometry
        """
        partBundleDict = self.__partBundleDict.get(lodName)
        if not partBundleDict:
            Actor.notify.warning("no lod named: %s" % (lodName))
            return
        partDef = partBundleDict.get(partName)
        if partDef:
            partDef.partBundleNP.hide()
        else:
            Actor.notify.warning("no part named %s!" % (partName))

    def showPart(self, partName, lodName="lodRoot"):
        """
        Make the given part render while in the tree.
        NOTE: this will affect child geometry
        """
        partBundleDict = self.__partBundleDict.get(lodName)
        if not partBundleDict:
            Actor.notify.warning("no lod named: %s" % (lodName))
            return
        partDef = partBundleDict.get(partName)
        if partDef:
            partDef.partBundleNP.show()
        else:
            Actor.notify.warning("no part named %s!" % (partName))

    def showAllParts(self, partName, lodName="lodRoot"):
        """
        Make the given part and all its children render while in the tree.
        NOTE: this will affect child geometry
        """
        partBundleDict = self.__partBundleDict.get(lodName)
        if not partBundleDict:
            Actor.notify.warning("no lod named: %s" % (lodName))
            return
        partDef = partBundleDict.get(partName)
        if partDef:
            partDef.partBundleNP.show()
            partDef.partBundleNP.getChildren().show()
        else:
            Actor.notify.warning("no part named %s!" % (partName))

    def exposeJoint(self, node, partName, jointName, lodName="lodRoot",
                    localTransform = 0):
        """exposeJoint(self, NodePath, string, string, key="lodRoot")
        Starts the joint animating the indicated node.  As the joint
        animates, it will transform the node by the corresponding
        amount.  This will replace whatever matrix is on the node each
        frame.  The default is to expose the net transform from the root,
        but if localTransform is true, only the node's local transform
        from its parent is exposed."""
        partBundleDict = self.__partBundleDict.get(lodName)
        if not partBundleDict:
            Actor.notify.warning("no lod named: %s" % (lodName))
            return None

        subpartDef = self.__subpartDict.get(partName, Actor.SubpartDef(partName))

        partDef = partBundleDict.get(subpartDef.truePartName)
        if partDef:
            bundle = partDef.partBundle
        else:
            Actor.notify.warning("no part named %s!" % (partName))
            return None

        # Get a handle to the joint.
        joint = bundle.findChild(jointName)

        if node == None:
            node = self.attachNewNode(jointName)

        if (joint):
            if localTransform:
                joint.addLocalTransform(node.node())
            else:
                joint.addNetTransform(node.node())
        else:
            Actor.notify.warning("no joint named %s!" % (jointName))

        return node

    def stopJoint(self, partName, jointName, lodName="lodRoot"):
        """stopJoint(self, string, string, key="lodRoot")
        Stops the joint from animating external nodes.  If the joint
        is animating a transform on a node, this will permanently stop
        it.  However, this does not affect vertex animations."""
        partBundleDict = self.__partBundleDict.get(lodName)
        if not partBundleDict:
            Actor.notify.warning("no lod named: %s" % (lodName))
            return None

        subpartDef = self.__subpartDict.get(partName, Actor.SubpartDef(partName))

        partDef = partBundleDict.get(subpartDef.truePartName)
        if partDef:
            bundle = partDef.partBundle
        else:
            Actor.notify.warning("no part named %s!" % (partName))
            return None

        # Get a handle to the joint.
        joint = bundle.findChild(jointName)

        if (joint):
            joint.clearNetTransforms()
            joint.clearLocalTransforms()
        else:
            Actor.notify.warning("no joint named %s!" % (jointName))

    def getJoints(self, jointName):
        joints=[]
        for lod in self.__partBundleDict.values():
            for part in lod.values():
                partBundle=part.partBundle
                joint=partBundle.findChild(jointName)
                if(joint):
                    joints.append(joint)

        return joints
    
    def getJointTransform(self,partName, jointName, lodName='lodRoot'):
        partBundleDict=self.__partBundleDict.get(lodName)
        if not partBundleDict:
            Actor.notify.warning("no lod named: %s" % (lodName))
            return None

        subpartDef = self.__subpartDict.get(partName, Actor.SubpartDef(partName))
        partDef = partBundleDict.get(subpartDef.truePartName)
        if partDef:
            bundle = partDef.partBundle
        else:
            Actor.notify.warning("no part named %s!" % (partName))
            return None

        joint = bundle.findChild(jointName)
        if joint == None:
            Actor.notify.warning("no joint named %s!" % (jointName))
            return None
        return joint.getInitialValue()


    def controlJoint(self, node, partName, jointName, lodName="lodRoot"):
        """controlJoint(self, NodePath, string, string, key="lodRoot")

        The converse of exposeJoint: this associates the joint with
        the indicated node, so that the joint transform will be copied
        from the node to the joint each frame.  This can be used for
        programmer animation of a particular joint at runtime.

        This must be called before any animations are played.  Once an
        animation has been loaded and bound to the character, it will
        be too late to add a new control during that animation.
        """
        partBundleDict=self.__partBundleDict.get(lodName)

        if not partBundleDict:
            Actor.notify.warning("no lod named: %s" % (lodName))
            return None
        
        subpartDef = self.__subpartDict.get(partName, Actor.SubpartDef(partName))
        partDef = partBundleDict.get(subpartDef.truePartName)
        if partDef:
            bundle = partDef.partBundle
            bundle.setModifiesAnimBundles(1)
        else:
            Actor.notify.warning("no part named %s!" % (partName))
            return None

        joint = bundle.findChild(jointName)
        if joint == None:
            Actor.notify.warning("no joint named %s!" % (jointName))
            return None

        if node == None:
            node = self.attachNewNode(jointName)
            if joint.getType().isDerivedFrom(MovingPartMatrix.getClassType()):
                node.setMat(joint.getInitialValue())

        # Store a dictionary of jointName: node to list the controls
        # requested for joints.  The controls will actually be applied
        # later, when we load up the animations in bindAnim().
        if self.__controlJoints.has_key(bundle.this):
            self.__controlJoints[bundle.this][jointName] = node
        else:
            self.__controlJoints[bundle.this] = { jointName: node }

        return node

    #This is an alternate method to control joints, which can be copied
    #This function is optimal in a non control jointed actor 
    def freezeJoint(self, partName, jointName, pos=Vec3(0,0,0), hpr=Vec3(0,0,0), scale=Vec3(1,1,1)):
        transform=Mat4(TransformState.makePosHprScale(pos,hpr,scale).getMat())
        #trueName = self.__subpartDict[partName].truePartName
        subpartDef = self.__subpartDict.get(partName, Actor.SubpartDef(partName))
        trueName = subpartDef.truePartName
        for bundleDict in self.__partBundleDict.values():     
            bundleDict[trueName].partBundle.freezeJoint(jointName, transform)
            

    def instance(self, path, partName, jointName, lodName="lodRoot"):
        """instance(self, NodePath, string, string, key="lodRoot")
        Instance a nodePath to an actor part at a joint called jointName"""
        partBundleDict = self.__partBundleDict.get(lodName)
        if partBundleDict:
            subpartDef = self.__subpartDict.get(partName, Actor.SubpartDef(partName))
            partDef = partBundleDict.get(subpartDef.truePartName)
            if partDef:
                joint = partDef.partBundleNP.find("**/" + jointName)
                if (joint.isEmpty()):
                    Actor.notify.warning("%s not found!" % (jointName))
                else:
                    return path.instanceTo(joint)
            else:
                Actor.notify.warning("no part named %s!" % (partName))
        else:
            Actor.notify.warning("no lod named %s!" % (lodName))

    def attach(self, partName, anotherPartName, jointName, lodName="lodRoot"):
        """attach(self, string, string, string, key="lodRoot")
        Attach one actor part to another at a joint called jointName"""
        partBundleDict = self.__partBundleDict.get(lodName)
        if partBundleDict:
            subpartDef = self.__subpartDict.get(partName, Actor.SubpartDef(partName))
            partDef = partBundleDict.get(subpartDef.truePartName)
            if partDef:
                anotherPartDef = partBundleDict.get(anotherPartName)
                if anotherPartDef:
                    joint = anotherPartDef.partBundleNP.find("**/" + jointName)
                    if (joint.isEmpty()):
                        Actor.notify.warning("%s not found!" % (jointName))
                    else:
                        partDef.partBundleNP.reparentTo(joint)
                else:
                    Actor.notify.warning("no part named %s!" % (anotherPartName))
            else:
                Actor.notify.warning("no part named %s!" % (partName))
        else:
            Actor.notify.warning("no lod named %s!" % (lodName))


    def drawInFront(self, frontPartName, backPartName, mode,
                    root=None, lodName=None):
        """drawInFront(self, string, int, string=None, key=None)

        Arrange geometry so the frontPart(s) are drawn in front of
        backPart.

        If mode == -1, the geometry is simply arranged to be drawn in
        the correct order, assuming it is already under a
        direct-render scene graph (like the DirectGui system).  That
        is, frontPart is reparented to backPart, and backPart is
        reordered to appear first among its siblings.

        If mode == -2, the geometry is arranged to be drawn in the
        correct order, and depth test/write is turned off for
        frontPart.

        If mode == -3, frontPart is drawn as a decal onto backPart.
        This assumes that frontPart is mostly coplanar with and does
        not extend beyond backPart, and that backPart is mostly flat
        (not self-occluding).

        If mode > 0, the frontPart geometry is placed in the 'fixed'
        bin, with the indicated drawing order.  This will cause it to
        be drawn after almost all other geometry.  In this case, the
        backPartName is actually unused.

        Takes an optional argument root as the start of the search for the
        given parts. Also takes optional lod name to refine search for the
        named parts. If root and lod are defined, we search for the given
        root under the given lod.
        """
        # check to see if we are working within an lod
        if lodName != None:
            # find the named lod node
            lodRoot = self.find("**/" + str(lodName))
            if root == None:
                # no need to look further
                root = lodRoot
            else:
                # look for root under lod
                root = lodRoot.find("**/" + root)
        else:
            # start search from self if no root and no lod given
            if root == None:
                root = self

        frontParts = root.findAllMatches("**/" + frontPartName)

        if mode > 0:
            # Use the 'fixed' bin instead of reordering the scene
            # graph.
            numFrontParts = frontParts.getNumPaths()
            for partNum in range(0, numFrontParts):
                frontParts[partNum].setBin('fixed', mode)
            return

        if mode == -2:
            # Turn off depth test/write on the frontParts.
            numFrontParts = frontParts.getNumPaths()
            for partNum in range(0, numFrontParts):
                frontParts[partNum].setDepthWrite(0)
                frontParts[partNum].setDepthTest(0)

        # Find the back part.
        backPart = root.find("**/" + backPartName)
        if (backPart.isEmpty()):
            Actor.notify.warning("no part named %s!" % (backPartName))
            return

        if mode == -3:
            # Draw as a decal.
            backPart.node().setEffect(DecalEffect.make())
        else:
            # Reorder the backPart to be the first of its siblings.
            backPart.reparentTo(backPart.getParent(), -1)

        #reparent all the front parts to the back part
        frontParts.reparentTo(backPart)


    def fixBounds(self, part=None):
        """fixBounds(self, nodePath=None)
        Force recomputation of bounding spheres for all geoms
        in a given part. If no part specified, fix all geoms
        in this actor
        """
        # if no part name specified fix all parts
        if (part==None):
            part = self

        # update all characters first
        charNodes = part.findAllMatches("**/+Character")
        numCharNodes = charNodes.getNumPaths()
        for charNum in range(0, numCharNodes):
            (charNodes.getPath(charNum)).node().update()

        # for each geomNode, iterate through all geoms and force update
        # of bounding spheres by marking current bounds as stale
        geomNodes = part.findAllMatches("**/+GeomNode")
        numGeomNodes = geomNodes.getNumPaths()
        for nodeNum in range(0, numGeomNodes):
            thisGeomNode = geomNodes.getPath(nodeNum)
            numGeoms = thisGeomNode.node().getNumGeoms()
            for geomNum in range(0, numGeoms):
                thisGeom = thisGeomNode.node().getGeom(geomNum)
                thisGeom.markBoundsStale()
                assert Actor.notify.debug("fixing bounds for node %s, geom %s" % \
                                          (nodeNum, geomNum))
            thisGeomNode.node().markInternalBoundsStale()

    def showAllBounds(self):
        """
        Show the bounds of all actor geoms
        """
        geomNodes = self.__geomNode.findAllMatches("**/+GeomNode")
        numGeomNodes = geomNodes.getNumPaths()

        for nodeNum in range(0, numGeomNodes):
            geomNodes.getPath(nodeNum).showBounds()

    def hideAllBounds(self):
        """
        Hide the bounds of all actor geoms
        """
        geomNodes = self.__geomNode.findAllMatches("**/+GeomNode")
        numGeomNodes = geomNodes.getNumPaths()

        for nodeNum in range(0, numGeomNodes):
            geomNodes.getPath(nodeNum).hideBounds()


    # actions
    def animPanel(self):
        from direct.showbase import TkGlobal
        from direct.tkpanels import AnimPanel
        return AnimPanel.AnimPanel(self)

    def stop(self, animName=None, partName=None):
        """stop(self, string=None, string=None)
        Stop named animation on the given part of the actor.
        If no name specified then stop all animations on the actor.
        NOTE: stops all LODs"""
        for control in self.getAnimControls(animName, partName):
            control.stop()

    def play(self, animName, partName=None, fromFrame=None, toFrame=None):
        """play(self, string, string=None)
        Play the given animation on the given part of the actor.
        If no part is specified, try to play on all parts. NOTE:
        plays over ALL LODs"""
        if fromFrame == None:
            for control in self.getAnimControls(animName, partName):
                control.play()
        else:
            for control in self.getAnimControls(animName, partName):
                if toFrame == None:
                    control.play(fromFrame, control.getNumFrames() - 1)
                else:
                    control.play(fromFrame, toFrame)

    def loop(self, animName, restart=1, partName=None,
             fromFrame=None, toFrame=None):
        """loop(self, string, int=1, string=None)
        Loop the given animation on the given part of the actor,
        restarting at zero frame if requested. If no part name
        is given then try to loop on all parts. NOTE: loops on
        all LOD's
        """
    
        if fromFrame == None:
            for control in self.getAnimControls(animName, partName):
                control.loop(restart)
        else:
            for control in self.getAnimControls(animName, partName):
                if toFrame == None:
                    control.loop(restart, fromFrame, control.getNumFrames() - 1)
                else:
                    control.loop(restart, fromFrame, toFrame)

    def pingpong(self, animName, restart=1, partName=None,
                 fromFrame=None, toFrame=None):
        """pingpong(self, string, int=1, string=None)
        Loop the given animation on the given part of the actor,
        restarting at zero frame if requested. If no part name
        is given then try to loop on all parts. NOTE: loops on
        all LOD's"""
        if fromFrame == None:
            fromFrame = 0

        for control in self.getAnimControls(animName, partName):
            if toFrame == None:
                control.pingpong(restart, fromFrame, control.getNumFrames() - 1)
            else:
                control.pingpong(restart, fromFrame, toFrame)

    def pose(self, animName, frame, partName=None, lodName=None):
        """pose(self, string, int, string=None)
        Pose the actor in position found at given frame in the specified
        animation for the specified part. If no part is specified attempt
        to apply pose to all parts."""
        for control in self.getAnimControls(animName, partName, lodName):
            control.pose(frame)

    def setBlend(self, animBlend = None, frameBlend = None,
                 blendType = None, partName = None):
        """
        Changes the way the Actor handles blending of multiple
        different animations, and/or interpolation between consecutive
        frames.

        The animBlend and frameBlend parameters are boolean flags.
        You may set either or both to True or False.  If you do not
        specify them, they do not change from the previous value.
        
        When animBlend is True, multiple different animations may
        simultaneously be playing on the Actor.  This means you may
        call play(), loop(), or pose() on multiple animations and have
        all of them contribute to the final pose each frame.

        In this mode (that is, when animBlend is True), starting a
        particular animation with play(), loop(), or pose() does not
        implicitly make the animation visible; you must also call
        setControlEffect() for each animation you wish to use to
        indicate how much each animation contributes to the final
        pose.

        The frameBlend flag is unrelated to playing multiple
        animations.  It controls whether the Actor smoothly
        interpolates between consecutive frames of its animation (when
        the flag is True) or holds each frame until the next one is
        ready (when the flag is False).  The default value of
        frameBlend is controlled by the interpolate-frames Config.prc
        variable.

        In either case, you may also specify blendType, which controls
        the precise algorithm used to blend two or more different
        matrix values into a final result.  Different skeleton
        hierarchies may benefit from different algorithms.  The
        default blendType is controlled by the anim-blend-type
        Config.prc variable.
        """
        bundles = []
        
        for lodName, partBundleDict in self.__partBundleDict.items():
            if partName == None:
                for partDef in partBundleDict.values():
                    bundles.append(partDef.partBundle)

            else:
                subpartDef = self.__subpartDict.get(partName, Actor.SubpartDef(partName))
                partDef = partBundleDict.get(subpartDef.truePartName)
                if partDef != None:
                    bundles.append(partDef.partBundle)
                else:
                    Actor.notify.warning("Couldn't find part: %s" % (partName))

        for bundle in bundles:
            if blendType != None:
                bundle.setBlendType(blendType)
            if animBlend != None:
                bundle.setAnimBlendFlag(animBlend)
            if frameBlend != None:
                bundle.setFrameBlendFlag(frameBlend)

    def enableBlend(self, blendType = PartBundle.BTNormalizedLinear, partName = None):
        """
        Enables blending of multiple animations simultaneously.
        After this is called, you may call play(), loop(), or pose()
        on multiple animations and have all of them contribute to the
        final pose each frame.

        With blending in effect, starting a particular animation with
        play(), loop(), or pose() does not implicitly make the
        animation visible; you must also call setControlEffect() for
        each animation you wish to use to indicate how much each
        animation contributes to the final pose.

        This method is deprecated.  You should use setBlend() instead.
        """
        self.setBlend(animBlend = True, blendType = blendType, partName = partName)

    def disableBlend(self, partName = None):
        """
        Restores normal one-animation-at-a-time operation after a
        previous call to enableBlend().

        This method is deprecated.  You should use setBlend() instead.
        """
        self.setBlend(animBlend = False, partName = partName)

    def setControlEffect(self, animName, effect,
                         partName = None, lodName = None):
        """
        Sets the amount by which the named animation contributes to
        the overall pose.  This controls blending of multiple
        animations; it only makes sense to call this after a previous
        call to setBlend(animBlend = True).
        """        
        for control in self.getAnimControls(animName, partName, lodName):
            control.getPart().setControlEffect(control, effect)

    def getAnimFilename(self, animName, partName='modelRoot'):
        """
        getAnimFilename(self, animName)
        return the animFilename given the animName
        """
        if self.switches:
            lodName = str(self.switches.keys()[0])
        else:
            lodName = 'lodRoot'

        try:
            return self.__animControlDict[lodName][partName][animName].filename
        except:
            return None

    def getAnimControl(self, animName, partName=None, lodName=None):
        """
        getAnimControl(self, string, string, string="lodRoot")
        Search the animControl dictionary indicated by lodName for
        a given anim and part. If none specified, try the first part and lod.
        Return the animControl if present, or None otherwise
        """
    
        if not partName:
            partName = 'modelRoot'

        if not lodName:
            if self.switches:
                lodName = str(self.switches.keys()[0])
            else:
                lodName = 'lodRoot'

        partDict = self.__animControlDict.get(lodName)
        # if this assertion fails, named lod was not present
        assert partDict != None

        animDict = partDict.get(partName)
        if animDict == None:
            # part was not present
            Actor.notify.warning("couldn't find part: %s" % (partName))
        else:
            anim = animDict.get(animName)
            if anim == None:
                # anim was not present
                assert Actor.notify.debug("couldn't find anim: %s" % (animName))
                pass
            else:
                # bind the animation first if we need to
                if not isinstance(anim.animControl, AnimControl):
                    self.__bindAnimToPart(animName, partName, lodName)
                return anim.animControl

        return None

    def getAnimControls(self, animName=None, partName=None, lodName=None):
        """getAnimControls(self, string, string=None, string=None)

        Returns a list of the AnimControls that represent the given
        animation for the given part and the given lod.  If animName
        is omitted, the currently-playing animation (or all
        currently-playing animations) is returned.  If partName is
        omitted, all parts are returned (or possibly the one overall
        Actor part, according to the subpartsComplete flag).  If
        lodName is omitted, all LOD's are returned.
        """

        if partName == None and self.__subpartsComplete:
            # If we have the __subpartsComplete flag, and no partName
            # is specified, it really means to play the animation on
            # all subparts, not on the overall Actor.
            partName = self.__subpartDict.keys()
            
        controls = []
        # build list of lodNames and corresponding animControlDicts
        # requested.
        if lodName == None:
            # Get all LOD's
            animControlDictItems = self.__animControlDict.items()
        else:
            partDict = self.__animControlDict.get(lodName)
            if partDict == None:
                Actor.notify.warning("couldn't find lod: %s" % (lodName))
                animControlDictItems = []
            else:
                animControlDictItems = [(lodName, partDict)]

        for lodName, partDict in animControlDictItems:
            # Now, build the list of partNames and the corresponding
            # animDicts.
            if partName == None:
                # Get all main parts, but not sub-parts.
                animDictItems = []
                for thisPart, animDict in partDict.items():
                    if not self.__subpartDict.has_key(thisPart):
                        animDictItems.append((thisPart, animDict))

            else:
                # Get exactly the named part or parts.
                if isinstance(partName, types.StringTypes):
                    partNameList = [partName]
                else:
                    partNameList = partName

                animDictItems = []
                
                for pName in partNameList:
                    animDict = partDict.get(pName)
                    if animDict == None:
                        # Maybe it's a subpart that hasn't been bound yet.
                        subpartDef = self.__subpartDict.get(pName)
                        if subpartDef:
                            animDict = {}
                            partDict[pName] = animDict

                    if animDict == None:
                        # part was not present
                        Actor.notify.warning("couldn't find part: %s" % (pName))
                    else:
                        animDictItems.append((pName, animDict))

            if animName == None:
                # get all playing animations
                for thisPart, animDict in animDictItems:
                    for anim in animDict.values():
                        if isinstance(anim.animControl, AnimControl) and anim.animControl.isPlaying():
                            controls.append(anim.animControl)
            else:
                # get the named animation only.
                for thisPart, animDict in animDictItems:
                    anim = animDict.get(animName)
                    if anim == None and partName != None:
                        for pName in partNameList:
                            # Maybe it's a subpart that hasn't been bound yet.
                            subpartDef = self.__subpartDict.get(pName)
                            if subpartDef:
                                truePartName = subpartDef.truePartName
                                anim = partDict[truePartName].get(animName)
                                if anim:
                                    anim = anim.makeCopy()
                                    animDict[animName] = anim

                    if anim == None:
                        # anim was not present
                        assert Actor.notify.debug("couldn't find anim: %s" % (animName))
                        pass
                    else:
                        # bind the animation first if we need to
                        animControl = anim.animControl
                        if animControl == None:
                            animControl = self.__bindAnimToPart(animName, thisPart, lodName)
                        if animControl:
                            controls.append(animControl)

        return controls

    def loadModel(self, modelPath, partName="modelRoot", lodName="lodRoot", copy = 1):
        """loadModel(self, string, string="modelRoot", string="lodRoot",
        bool = 0)
        Actor model loader. Takes a model name (ie file path), a part
        name(defaults to "modelRoot") and an lod name(defaults to "lodRoot").
        If copy is set to 0, do a loadModel instead of a loadModelCopy.
        """
        assert partName not in self.__subpartDict

        assert Actor.notify.debug("in loadModel: %s, part: %s, lod: %s, copy: %s" % \
                                  (modelPath, partName, lodName, copy))

        if isinstance(modelPath, NodePath):
            # If we got a NodePath instead of a string, use *that* as
            # the model directly.
            if (copy):
                model = modelPath.copyTo(NodePath())
            else:
                model = modelPath
        else:
            # otherwise, we got the name of the model to load.
            loaderOptions = self.modelLoaderOptions
            if not copy:
                # If copy = 0, then we should always hit the disk.
                loaderOptions = LoaderOptions(loaderOptions)
                loaderOptions.setFlags(loaderOptions.getFlags() & ~LoaderOptions.LFNoRamCache)
            
            # Pass loaderOptions to specify that we want to
            # get the skeleton model.  This only matters to model
            # files (like .mb) for which we can choose to extract
            # either the skeleton or animation, or neither.
            model = loader.loadModel(modelPath, loaderOptions = loaderOptions)

        if (model == None):
            raise StandardError, "Could not load Actor model %s" % (modelPath)

        if (model.node().isOfType(PartBundleNode.getClassType())):
            bundleNP = model
        else:
            bundleNP = model.find("**/+PartBundleNode")
            
        if (bundleNP.isEmpty()):
            Actor.notify.warning("%s is not a character!" % (modelPath))
            model.reparentTo(self.__geomNode)
        else:
            # Maybe the model file also included some animations.  If
            # so, try to bind them immediately and put them into the
            # animControlDict.
            acc = AnimControlCollection()
            autoBind(model.node(), acc, ~0)
            numAnims = acc.getNumAnims()

            # Now extract out the PartBundleNode and integrate it with
            # the Actor.
            self.__prepareBundle(bundleNP, model, partName, lodName)

            if numAnims != 0:
                # If the model had some animations, store them in the
                # dict so they can be played.
                Actor.notify.info("model contains %s animations." % (numAnims))

                # make sure this lod is in anim control dict
                self.__animControlDict.setdefault(lodName, {})
                self.__animControlDict[lodName].setdefault(partName, {})

                for i in range(numAnims):
                    animControl = acc.getAnim(i)
                    animName = acc.getAnimName(i)

                    # Now we've already bound the animation, but we
                    # have no associated filename.  So store the
                    # animControl, but put None in for the filename.
                    animDef = Actor.AnimDef(None)
                    animDef.animControl = animControl
                    self.__animControlDict[lodName][partName][animName] = animDef

    def __prepareBundle(self, bundleNP, model,
                        partName="modelRoot", lodName="lodRoot"):
        assert partName not in self.__subpartDict

        # Rename the node at the top of the hierarchy, if we
        # haven't already, to make it easier to identify this
        # actor in the scene graph.
        if not self.gotName:
            self.node().setName(bundleNP.node().getName())
            self.gotName = 1

        # we rename this node to make Actor copying easier
        bundleNP.node().setName("%s%s"%(Actor.partPrefix,partName))

        if (self.__partBundleDict.has_key(lodName) == 0):
            # make a dictionary to store these parts in
            needsDict = 1
            bundleDict = {}
        else:
            needsDict = 0

        if (lodName!="lodRoot"):
            # parent to appropriate node under LOD switch
            bundleNP.reparentTo(self.__LODNode.find("**/%s"%lodName))
        else:
            bundleNP.reparentTo(self.__geomNode)

        node = bundleNP.node()
        # A model loaded from disk will always have just one bundle.
        assert(node.getNumBundles() == 1)
        bundle = node.getBundle(0)
        self.__frozenJoints[bundle.this]={}
        if (needsDict):
            bundleDict[partName] = Actor.PartDef(bundleNP, bundle, model.node())
            self.__partBundleDict[lodName] = bundleDict
            self.__updateSortedLODNames()
        else:
            self.__partBundleDict[lodName][partName] = Actor.PartDef(bundleNP, bundle, model.node())

    def makeSubpart(self, partName, includeJoints, excludeJoints = [],
                    parent="modelRoot"):

        """Defines a new "part" of the Actor that corresponds to the
        same geometry as the named parent part, but animates only a
        certain subset of the joints.  This can be used for
        partial-body animations, for instance to animate a hand waving
        while the rest of the body continues to play its walking
        animation.

        includeJoints is a list of joint names that are to be animated
        by the subpart.  Each name can include globbing characters
        like '?' or '*', which will match one or any number of
        characters, respectively.  Including a joint by naming it in
        includeJoints implicitly includes all of the descendents of
        that joint as well, except for excludeJoints, below.

        excludeJoints is a list of joint names that are *not* to be
        animated by the subpart.  As in includeJoints, each name can
        include globbing characters.  If a joint is named by
        excludeJoints, it will not be included (and neither will any
        of its descendents), even if a parent joint was named by
        includeJoints.

        parent is the actual partName that this subpart is based
        on."""

        assert partName not in self.__subpartDict

        subpartDef = self.__subpartDict.get(parent, Actor.SubpartDef(''))

        subset = PartSubset(subpartDef.subset)
        for name in includeJoints:
            subset.addIncludeJoint(GlobPattern(name))
        for name in excludeJoints:
            subset.addExcludeJoint(GlobPattern(name))

        self.__subpartDict[partName] = Actor.SubpartDef(parent, subset)

    def setSubpartsComplete(self, flag):

        """Sets the subpartsComplete flag.  This affects the behavior
        of play(), loop(), stop(), etc., when no explicit parts are
        specified.

        When this flag is False (the default), play() with no parts
        means to play the animation on the overall Actor, which is a
        separate part that overlaps each of the subparts.  If you then
        play a different animation on a subpart, it may stop the
        overall animation (in non-blend mode) or blend with it (in
        blend mode).

        When this flag is True, play() with no parts means to play the
        animation on each of the subparts--instead of on the overall
        Actor.  In this case, you may then play a different animation
        on a subpart, which replaces only that subpart's animation.

        It makes sense to set this True when the union of all of your
        subparts completely defines the entire Actor.
        """
        
        self.__subpartsComplete = flag

    def getSubpartsComplete(self):
        """See setSubpartsComplete()."""
        
        return self.__subpartsComplete

    def loadAnims(self, anims, partName="modelRoot", lodName="lodRoot"):
        """loadAnims(self, string:string{}, string='modelRoot',
        string='lodRoot')
        Actor anim loader. Takes an optional partName (defaults to
        'modelRoot' for non-multipart actors) and lodName (defaults
        to 'lodRoot' for non-LOD actors) and dict of corresponding
        anims in the form animName:animPath{}
        """
        reload = True
        if (lodName == 'all'):
            reload = False
            lodNames = self.switches.keys()
            lodNames.sort()
            for i in range(0,len(lodNames)):
                lodNames[i] = str(lodNames[i])
        else:
            lodNames = [lodName]
            
        assert Actor.notify.debug("in loadAnims: %s, part: %s, lod: %s" %
                                  (anims, partName, lodNames[0]))

        firstLoad = True
        if not reload:
            try:
                self.__animControlDict[lodNames[0]][partName]
                firstLoad = False
            except:
                pass
        for lName in lodNames:
            if firstLoad:
                self.__animControlDict.setdefault(lName, {})
                self.__animControlDict[lName].setdefault(partName, {})

        for animName, filename in anims.items():
            # make sure this lod is in anim control dict
            for lName in lodNames:
                # store the file path only; we will bind it (and produce
                # an AnimControl) when it is played
                if not firstLoad:
                    self.__animControlDict[lName][partName][animName].filename = filename
                else:
                    self.__animControlDict[lName][partName][animName] = Actor.AnimDef(filename)

    def initAnimsOnAllLODs(self,partNames):
        
        for lod in self.__partBundleDict.keys():
            for part in partNames:
                self.__animControlDict.setdefault(lod,{})
                self.__animControlDict[lod].setdefault(part, {})

        #for animName, filename in anims.items():
        #    # make sure this lod is in anim control dict
        #    for lod in self.__partBundleDict.keys():
        #        # store the file path only; we will bind it (and produce
        #        # an AnimControl) when it is played
        #        
        #        self.__animControlDict[lod][partName][animName] = Actor.AnimDef(filename)
                
    def loadAnimsOnAllLODs(self, anims,partName="modelRoot"):
        """loadAnims(self, string:string{}, string='modelRoot',
        string='lodRoot')
        Actor anim loader. Takes an optional partName (defaults to
        'modelRoot' for non-multipart actors) and lodName (defaults
        to 'lodRoot' for non-LOD actors) and dict of corresponding
        anims in the form animName:animPath{}
        """
            
        for animName, filename in anims.items():
            # make sure this lod is in anim control dict
            for lod in self.__partBundleDict.keys():
                # store the file path only; we will bind it (and produce
                # an AnimControl) when it is played
                
                self.__animControlDict[lod][partName][animName]= Actor.AnimDef(filename)

                
    def unloadAnims(self, anims, partName="modelRoot", lodName="lodRoot"):
        """unloadAnims(self, string:string{}, string='modelRoot',
        string='lodRoot')
        Actor anim unloader. Takes an optional partName (defaults to
        'modelRoot' for non-multipart actors) and lodName (defaults
        to 'lodRoot' for non-LOD actors) and dict of corresponding
        anims in the form animName:animPath{}. Deletes the anim control
        for the given animation and parts/lods.
        """
        assert Actor.notify.debug("in unloadAnims: %s, part: %s, lod: %s" %
                                  (anims, partName, lodName))

        if (lodName == None):
            lodNames = self.__animControlDict.keys()
        else:
            lodNames = [lodName]

        if (partName == None):
            if len(lodNames) > 0:
                partNames = self.__animControlDict[lodNames[0]].keys()
            else:
                partNames = []
        else:
            partNames = [partName]

        if (anims==None):
            if len(lodNames) > 0 and len(partNames) > 0:
                anims = self.__animControlDict[lodNames[0]][partNames[0]].keys()
            else:
                anims = []

        for lodName in lodNames:
            for partName in partNames:
                for animName in anims:
                    # delete the anim control
                    try:
                        animDef = self.__animControlDict[lodName][partName][animName]
                        if animDef.animControl != None:
                            # Try to clear any control effects before we let
                            # our handle on them go. This is especially
                            # important if the anim control was blending
                            # animations.
                            animDef.animControl.getPart().clearControlEffects()
                            animDef.animControl = None
                            animDef.animModel = None
                    except:
                        return

    def bindAnim(self, animName, partName="modelRoot", lodName="lodRoot"):
        """bindAnim(self, string, string='modelRoot', string='lodRoot')
        Bind the named animation to the named part and lod
        """
        if lodName == None:
            lodNames = self.__animControlDict.keys()
        else:
            lodNames = [lodName]

        # loop over all lods
        for thisLod in lodNames:
            if partName == None:
                partNames = self.__partBundleDict[thisLod].keys()
            else:
                partNames = [partName]
            # loop over all parts
            for thisPart in partNames:
                ac = self.__bindAnimToPart(animName, thisPart, thisLod)


    def __bindAnimToPart(self, animName, partName, lodName):
        """
        for internal use only!
        """
        # make sure this anim is in the dict
        subpartDef = self.__subpartDict.get(partName, Actor.SubpartDef(partName))

        partDict = self.__animControlDict[lodName]
        animDict = partDict.get(partName)
        if animDict == None:
            # It must be a subpart that hasn't been bound yet.
            animDict = {}
            partDict[partName] = animDict

        anim = animDict.get(animName)
        if anim == None:
            # It must be a subpart that hasn't been bound yet.
            anim = partDict[subpartDef.truePartName].get(animName)
            anim = anim.makeCopy()
            animDict[animName] = anim

        if anim == None:
            Actor.notify.error("actor has no animation %s", animName)

        # only bind if not already bound!
        if anim.animControl:
            return anim.animControl

        # fetch a copy from the modelPool, or if we weren't careful
        # enough to preload, fetch from disk
        animPath = anim.filename
        loaderOptions = self.animLoaderOptions
        if not self.__autoCopy:
            # If copy = 0, then we should always hit the disk.
            loaderOptions = LoaderOptions(loaderOptions)
            loaderOptions.setFlags(loaderOptions.getFlags() & ~LoaderOptions.LFNoRamCache)
            
        animNode = loader.loadModel(animPath, loaderOptions = loaderOptions)
        if animNode == None:
            return None
        animBundle = (animNode.find("**/+AnimBundleNode").node()).getBundle()

        bundle = self.__partBundleDict[lodName][subpartDef.truePartName].partBundle

        #NOTE: this is up here until we can guarantee anim bundle copying at a lower level
        # Before we apply any control joints, we have to make a
        # copy of the bundle hierarchy, so we don't modify other
        # Actors that share the same bundle.



        # Are there any controls requested for joints in this bundle?
        # If so, apply them.
        assert Actor.notify.debug('actor bundle %s, %s'% (bundle,bundle.this))
        controlDict = self.__controlJoints.get(bundle.this, None)

        animBundle = animBundle.copyBundle()

        if controlDict:
            for jointName, node in controlDict.items():
                if node:
                    joint = animBundle.makeChildDynamic(jointName)
                    if joint:
                        joint.setValueNode(node.node())
                    else:
                        Actor.notify.error("controlled joint %s is not present" % jointName)

        # bind anim
        animControl = bundle.bindAnim(animBundle, -1, subpartDef.subset)

        if (animControl == None):
            Actor.notify.error("Null AnimControl: %s" % (animName))
        else:
            # store the animControl
            anim.animControl = animControl
            anim.animModel = animNode.node()
            assert Actor.notify.debug("binding anim: %s to part: %s, lod: %s" %
                                      (animName, partName, lodName))
        return animControl

    def __copyPartBundles(self, other):
        """__copyPartBundles(self, Actor)
        Copy the part bundle dictionary from another actor as this
        instance's own. NOTE: this method does not actually copy geometry
        """
        for lodName in other.__partBundleDict.keys():
            self.__partBundleDict[lodName] = {}
            self.__updateSortedLODNames()
            # find the lod Asad
            if lodName == 'lodRoot':
                partLod = self
            else:
                partLod = self.find("**/%s"%lodName)
            if partLod.isEmpty():
                Actor.notify.warning("no lod named: %s" % (lodName))
                return None
            for partName, partDef in other.__partBundleDict[lodName].items():
                model = partDef.partModel.copySubgraph()

                # We can really only copy from a non-flattened avatar.
                assert partDef.partBundleNP.node().getNumBundles() == 1
                
                # find the part in our tree
                bundleNP = partLod.find("**/%s%s"%(Actor.partPrefix,partName))
                if (bundleNP != None):
                    # store the part bundle
                    assert bundleNP.node().getNumBundles() == 1
                    bundle = bundleNP.node().getBundle(0)
                    otherFixed=other.__frozenJoints.get(partDef.partBundle.this,None)
                    if(otherFixed is not None):
                        self.__frozenJoints[bundle.this]=copy.copy(otherFixed)
                    self.__partBundleDict[lodName][partName] = Actor.PartDef(bundleNP, bundle, model)
                else:
                    Actor.notify.error("lod: %s has no matching part: %s" %
                                       (lodName, partName))

    def __copySubpartDict(self, other):
        """Copies the subpartDict from another as this instance's own.
        This makes a deep copy of the map and all of the names and
        PartSubset objects within it.  We can't use copy.deepcopy()
        because of the included C++ PartSubset objects."""

        self.__subpartDict = {}
        for partName, subpartDef in other.__subpartDict.items():
            subpartDefCopy = subpartDef
            if subpartDef:
                subpartDef = subpartDef.makeCopy()
            self.__subpartDict[partName] = subpartDef

    def __copyAnimControls(self, other):
        """__copyAnimControls(self, Actor)
        Get the anims from the anim control's in the anim control
        dictionary of another actor. Bind these anim's to the part
        bundles in our part bundle dict that have matching names, and
        store the resulting anim controls in our own part bundle dict"""
        for lodName in other.__animControlDict.keys():
            self.__animControlDict[lodName] = {}
            for partName in other.__animControlDict[lodName].keys():
                self.__animControlDict[lodName][partName] = {}
                for animName in other.__animControlDict[lodName][partName].keys():
                    anim = other.__animControlDict[lodName][partName][animName]
                    anim = anim.makeCopy()
                    self.__animControlDict[lodName][partName][animName] = anim


    def actorInterval(self, *args, **kw):
        from direct.interval import ActorInterval
        return ActorInterval.ActorInterval(self, *args, **kw)

    def getAnimBlends(self, animName=None, partName=None, lodName=None):
        """ Returns a list of the form:

        [ (lodName, [(animName, [(partName, effect), (partName, effect), ...]),
                     (animName, [(partName, effect), (partName, effect), ...]),
                     ...]),
          (lodName, [(animName, [(partName, effect), (partName, effect), ...]),
                     (animName, [(partName, effect), (partName, effect), ...]),
                     ...]),
           ... ]

        This list reports the non-zero control effects for each
        partName within a particular animation and LOD. """

        result = []

        if animName is None:
            animNames = self.getAnimNames()
        else:
            animNames = [animName]

        if lodName is None:
            lodNames = self.getLODNames()
        else:
            lodNames = [lodName]

        if partName == None and self.__subpartsComplete:
            partNames = self.__subpartDict.keys()
        else:
            partNames = [partName]

        for lodName in lodNames:
            animList = []
            for animName in animNames:
                blendList = []
                for partName in partNames:
                    control = self.getAnimControl(animName, partName, lodName)
                    if control:
                        part = control.getPart()
                        effect = part.getControlEffect(control)
                        if effect > 0.:
                            blendList.append((partName, effect))
                if blendList:
                    animList.append((animName, blendList))
            if animList:
                result.append((lodName, animList))

        return result
    
    def printAnimBlends(self, animName=None, partName=None, lodName=None):
        for lodName, animList in self.getAnimBlends(animName, partName, lodName):
            print 'LOD %s:' % (lodName)
            for animName, blendList in animList:

                list = []
                for partName, effect in blendList:
                    list.append('%s:%.3f' % (partName, effect))
                print '  %s: %s' % (animName, ', '.join(list))

    def osdAnimBlends(self, animName=None, partName=None, lodName=None):
        if not onScreenDebug.enabled:
            return
        # puts anim blending info into the on-screen debug panel
        if animName is None:
            animNames = self.getAnimNames()
        else:
            animNames = [animName]
        for animName in animNames:
            if animName is 'nothing':
                continue
            thisAnim = ''
            totalEffect = 0.
            controls = self.getAnimControls(animName, partName, lodName)
            for control in controls:
                part = control.getPart()
                name = part.getName()
                effect = part.getControlEffect(control)
                if effect > 0.:
                    totalEffect += effect
                    thisAnim += ('%s:%.3f, ' % (name, effect))
            thisAnim += "\n"
            for control in controls:
                part = control.getPart()
                name = part.getName()
                rate = control.getPlayRate()
                thisAnim += ('%s:%.1f, ' % (name, rate))
            # don't display anything if this animation is not being played
            itemName = 'anim %s' % animName
            if totalEffect > 0.:
                onScreenDebug.add(itemName, thisAnim)
            else:
                if onScreenDebug.has(itemName):
                    onScreenDebug.remove(itemName)

    # these functions compensate for actors that are modeled facing the viewer but need
    # to face away from the camera in the game
    def faceAwayFromViewer(self):
        self.getGeomNode().setH(180)
    def faceTowardsViewer(self):
        self.getGeomNode().setH(0)

    def renamePartBundles(self, partName, newBundleName):
        subpartDef = self.__subpartDict.get(partName, Actor.SubpartDef(partName))
        for partBundleDict in self.__partBundleDict.values():
            partDef=partBundleDict.get(subpartDef.truePartName)
            partDef.partBundle.setName(newBundleName)
