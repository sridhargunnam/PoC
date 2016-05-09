# EMACS settings: -*-	tab-width: 2; indent-tabs-mode: t; python-indent-offset: 2 -*-
# vim: tabstop=2:shiftwidth=2:noexpandtab
# kate: tab-width 2; replace-tabs off; indent-width 2;
# 
# ==============================================================================
# Authors:          Patrick Lehmann
#                   Martin Zabel
# 
# Python Class:      TODO
# 
# Description:
# ------------------------------------
#		TODO:
#		- 
#		- 
#
# License:
# ==============================================================================
# Copyright 2007-2016 Technische Universitaet Dresden - Germany
#                     Chair for VLSI-Design, Diagnostics and Architecture
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#   http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
#
# entry point
from datetime import datetime

if __name__ != "__main__":
	# place library initialization code here
	pass
else:
	from lib.Functions import Exit
	Exit.printThisIsNoExecutableFile("The PoC-Library - Python Module Simulator.GHDLSimulator")


# load dependencies
from pathlib                import Path

from Base.Exceptions        import NotConfiguredException
from Base.Logging            import Severity
from Base.Project            import FileTypes, VHDLVersion, ToolChain, Tool
from Base.Simulator          import SimulatorException, Simulator as BaseSimulator, VHDL_TESTBENCH_LIBRARY_NAME, SimulationResult, SkipableSimulatorException, \
	SimulationState
from ToolChains.GHDL        import GHDL, GHDLException, GHDLReanalyzeException
from ToolChains.GTKWave      import GTKWave


class Simulator(BaseSimulator):
	_TOOL_CHAIN =            ToolChain.GHDL_GTKWave
	_TOOL =                  Tool.GHDL

	class __Directories__(BaseSimulator.__Directories__):
		GTKWBinary = None

	def __init__(self, host, guiMode):
		super().__init__(host)

		self._guiMode =        guiMode

		self._entity =        None
		self._testbenchFQN =  None
		self._vhdlGenerics =  None

		self._toolChain =      None

		ghdlFilesDirectoryName =        host.PoCConfig['CONFIG.DirectoryNames']['GHDLFiles']
		self.Directories.Working =      host.Directories.Temp / ghdlFilesDirectoryName
		self.Directories.PreCompiled =  host.Directories.PreCompiled / ghdlFilesDirectoryName

		if (guiMode is True):
			# prepare paths for GTKWave, if configured
			sectionName = 'INSTALL.GTKWave'
			if (len(host.PoCConfig.options(sectionName)) != 0):
				self.Directories.GTKWBinary = Path(host.PoCConfig[sectionName]['BinaryDirectory'])
			else:
				raise NotConfiguredException("No GHDL compatible waveform viewer is configured on this system.")

		self._PrepareSimulationEnvironment()
		self._PrepareSimulator()

	def _PrepareSimulator(self):
		# create the GHDL executable factory
		self._LogVerbose("Preparing GHDL simulator.")
		ghdlSection = self.Host.PoCConfig['INSTALL.GHDL']
		binaryPath = Path(ghdlSection['BinaryDirectory'])
		version = ghdlSection['Version']
		backend = ghdlSection['Backend']
		self._toolChain =      GHDL(self.Host.Platform, binaryPath, version, backend, logger=self.Logger)

	def Run(self, testbench, board, vhdlVersion, vhdlGenerics=None, guiMode=False):
		super().Run(testbench, board, vhdlVersion, vhdlGenerics)

		self._prepareTime = self._GetTimeDeltaSinceLastEvent()

		if (self._toolChain.Backend in ["gcc", "llvm"]):
			self._RunAnalysis()
			self._analyzeTime =     self._GetTimeDeltaSinceLastEvent()

			self._RunElaboration(testbench)
			self._elaborationTime = self._GetTimeDeltaSinceLastEvent()

			self._RunSimulation(testbench)
			self._simulationTime =  self._GetTimeDeltaSinceLastEvent()
		elif (self._toolChain.Backend == "mcode"):
			self._RunAnalysis()
			self._analyzeTime =     self._GetTimeDeltaSinceLastEvent()
			self._elaborationTime = self._GetTimeDeltaSinceLastEvent()

			self._RunSimulation(testbench)
			self._simulationTime =  self._GetTimeDeltaSinceLastEvent()

		# FIXME: a very quick implemenation
		if (guiMode is True):
			self._state = SimulationState.View
			viewer = self.GetViewer()
			viewer.View(testbench)

		self._endAt = datetime.now()

	def _RunAnalysis(self):
		self._LogNormal("Running analysis for every vhdl file...")
		self._state = SimulationState.Analyze
		
		# create a GHDLAnalyzer instance
		ghdl = self._toolChain.GetGHDLAnalyze()
		ghdl.Parameters[ghdl.FlagVerbose] =            (self.Logger.LogLevel is Severity.Debug)
		ghdl.Parameters[ghdl.FlagExplicit] =          True
		ghdl.Parameters[ghdl.FlagRelaxedRules] =      True
		ghdl.Parameters[ghdl.FlagWarnBinding] =        True
		ghdl.Parameters[ghdl.FlagNoVitalChecks] =      True
		ghdl.Parameters[ghdl.FlagMultiByteComments] =  True
		ghdl.Parameters[ghdl.FlagSynBinding] =        True
		ghdl.Parameters[ghdl.FlagPSL] =                True

		if (self._vhdlVersion == VHDLVersion.VHDL87):
			ghdl.Parameters[ghdl.SwitchVHDLVersion] =    "87"
			ghdl.Parameters[ghdl.SwitchIEEEFlavor] =    "synopsys"
		elif (self._vhdlVersion == VHDLVersion.VHDL93):
			ghdl.Parameters[ghdl.SwitchVHDLVersion] =    "93c"
			ghdl.Parameters[ghdl.SwitchIEEEFlavor] =    "synopsys"
		elif (self._vhdlVersion == VHDLVersion.VHDL02):
			ghdl.Parameters[ghdl.SwitchVHDLVersion] =    "02"
		elif (self._vhdlVersion == VHDLVersion.VHDL08):
			ghdl.Parameters[ghdl.SwitchVHDLVersion] =    "08"
		else:                                          raise SimulatorException("VHDL version is not supported.")

		# add external library references
		ghdl.Parameters[ghdl.ArgListLibraryReferences] = [str(extLibrary.Path) for extLibrary in self._pocProject.ExternalVHDLLibraries]
		
		# run GHDL analysis for each VHDL file
		for file in self._pocProject.Files(fileType=FileTypes.VHDLSourceFile):
			if (not file.Path.exists()):                  raise SkipableSimulatorException("Cannot analyse '{0!s}'.".format(file.Path)) from FileNotFoundError(str(file.Path))

			ghdl.Parameters[ghdl.SwitchVHDLLibrary] =      file.LibraryName
			ghdl.Parameters[ghdl.ArgSourceFile] =          file.Path
			try:
				ghdl.Analyze()
			except GHDLReanalyzeException as ex:
				raise SkipableSimulatorException("Error while analysing '{0!s}'.".format(file.Path)) from ex
			except GHDLException as ex:
				raise SimulatorException("Error while analysing '{0!s}'.".format(file.Path)) from ex
			if ghdl.HasErrors:
				raise SkipableSimulatorException("Error while analysing '{0!s}'.".format(file.Path))


	# running simulation
	# ==========================================================================
	def _RunElaboration(self, testbench):
		self._LogNormal("Running elaboration...")
		self._state = SimulationState.Elaborate
		
		# create a GHDLElaborate instance
		ghdl = self._toolChain.GetGHDLElaborate()
		ghdl.Parameters[ghdl.FlagVerbose] =            (self.Logger.LogLevel is Severity.Debug)
		ghdl.Parameters[ghdl.SwitchVHDLLibrary] =      VHDL_TESTBENCH_LIBRARY_NAME
		ghdl.Parameters[ghdl.ArgTopLevel] =            testbench.ModuleName
		ghdl.Parameters[ghdl.FlagExplicit] =          True

		# add external library references
		ghdl.Parameters[ghdl.ArgListLibraryReferences] = [str(extLibrary.Path) for extLibrary in self._pocProject.ExternalVHDLLibraries]

		if (self._vhdlVersion == VHDLVersion.VHDL87):
			ghdl.Parameters[ghdl.SwitchVHDLVersion] =    "87"
			ghdl.Parameters[ghdl.SwitchIEEEFlavor] =    "synopsys"
		elif (self._vhdlVersion == VHDLVersion.VHDL93):
			ghdl.Parameters[ghdl.SwitchVHDLVersion] =    "93c"
			ghdl.Parameters[ghdl.SwitchIEEEFlavor] =    "synopsys"
		elif (self._vhdlVersion == VHDLVersion.VHDL02):
			ghdl.Parameters[ghdl.SwitchVHDLVersion] =    "02"
		elif (self._vhdlVersion == VHDLVersion.VHDL08):
			ghdl.Parameters[ghdl.SwitchVHDLVersion] =    "08"
		else:                                          raise SimulatorException("VHDL version is not supported.")
		
		try:
			ghdl.Elaborate()
		except GHDLException as ex:
			raise SimulatorException("Error while elaborating '{0}.{1}'.".format(VHDL_TESTBENCH_LIBRARY_NAME, testbench.ModuleName)) from ex
		if ghdl.HasErrors:
			raise SkipableSimulatorException("Error while elaborating '{0}.{1}'.".format(VHDL_TESTBENCH_LIBRARY_NAME, testbench.ModuleName))
	
	
	def _RunSimulation(self, testbench):
		self._LogNormal("Running simulation...")
		self._state = SimulationState.Simulate
			
		# create a GHDLRun instance
		ghdl = self._toolChain.GetGHDLRun()
		ghdl.Parameters[ghdl.FlagVerbose] =             (self.Logger.LogLevel is Severity.Debug)
		ghdl.Parameters[ghdl.FlagExplicit] =            True
		ghdl.Parameters[ghdl.FlagRelaxedRules] =        True
		ghdl.Parameters[ghdl.FlagWarnBinding] =         True
		ghdl.Parameters[ghdl.FlagNoVitalChecks] =       True
		ghdl.Parameters[ghdl.FlagMultiByteComments] =   True
		ghdl.Parameters[ghdl.FlagSynBinding] =          True
		ghdl.Parameters[ghdl.FlagPSL] =                 True
		ghdl.Parameters[ghdl.SwitchVHDLLibrary] =       VHDL_TESTBENCH_LIBRARY_NAME
		ghdl.Parameters[ghdl.ArgTopLevel] =             testbench.ModuleName

		if (self._vhdlVersion == VHDLVersion.VHDL87):
			ghdl.Parameters[ghdl.SwitchVHDLVersion] =     "87"
			ghdl.Parameters[ghdl.SwitchIEEEFlavor] =      "synopsys"
		elif (self._vhdlVersion == VHDLVersion.VHDL93):
			ghdl.Parameters[ghdl.SwitchVHDLVersion] =     "93c"
			ghdl.Parameters[ghdl.SwitchIEEEFlavor] =      "synopsys"
		elif (self._vhdlVersion == VHDLVersion.VHDL02):
			ghdl.Parameters[ghdl.SwitchVHDLVersion] =     "02"
		elif (self._vhdlVersion == VHDLVersion.VHDL08):
			ghdl.Parameters[ghdl.SwitchVHDLVersion] =     "08"
		else:                                           raise SimulatorException("VHDL version is not supported.")

		# add external library references
		ghdl.Parameters[ghdl.ArgListLibraryReferences] = [str(extLibrary.Path) for extLibrary in self._pocProject.ExternalVHDLLibraries]

		# configure RUNOPTS
		ghdl.RunOptions[ghdl.SwitchIEEEAsserts] = "disable-at-0"		# enable, disable, disable-at-0
		# set dump format to save simulation results to *.vcd file
		if (self._guiMode):
			waveformFileFormat =  self.Host.PoCConfig[testbench.ConfigSectionName]['ghdlWaveformFileFormat']
			if (waveformFileFormat == "vcd"):
				waveformFilePath = self.Directories.Working / (testbench.ModuleName + ".vcd")
				ghdl.RunOptions[ghdl.SwitchVCDWaveform] =    waveformFilePath
			elif (waveformFileFormat == "vcdgz"):
				waveformFilePath = self.Directories.Working / (testbench.ModuleName + ".vcd.gz")
				ghdl.RunOptions[ghdl.SwitchVCDGZWaveform] =  waveformFilePath
			elif (waveformFileFormat == "fst"):
				waveformFilePath = self.Directories.Working / (testbench.ModuleName + ".fst")
				ghdl.RunOptions[ghdl.SwitchFSTWaveform] =    waveformFilePath
			elif (waveformFileFormat == "ghw"):
				waveformFilePath = self.Directories.Working / (testbench.ModuleName + ".ghw")
				ghdl.RunOptions[ghdl.SwitchGHDLWaveform] =  waveformFilePath
			else:                                            raise SimulatorException("Unknown waveform file format for GHDL.")
		
		testbench.Result = ghdl.Run()

	# def _ExecuteSimulation(self, testbench):
	# 	self._LogNormal("Executing simulation...")
	#
	# 	# create a GHDLRun instance
	# 	ghdl = self._toolChain.GetGHDLRun()
	# 	ghdl.VHDLVersion =  self._vhdlVersion
	# 	ghdl.VHDLLibrary =  VHDL_TESTBENCH_LIBRARY_NAME
	#
	# 	# configure RUNOPTS
	# 	runOptions = []
	# 	runOptions.append('--ieee-asserts={0}'.format("disable-at-0"))		# enable, disable, disable-at-0
	# 	# set dump format to save simulation results to *.vcd file
	# 	if (self._guiMode):
	# 		waveformFileFormat =  self.Host.PoCConfig[testbench.ConfigSectionName]['ghdlWaveformFileFormat']
	#
	# 		if (waveformFileFormat == "vcd"):
	# 			waveformFilePath = self.Directories.Working / (testbench.ModuleName + ".vcd")
	# 			runOptions.append("--vcd={0!s}".format(waveformFilePath))
	# 		elif (waveformFileFormat == "vcdgz"):
	# 			waveformFilePath = self.Directories.Working / (testbench.ModuleName + ".vcd.gz")
	# 			runOptions.append("--vcdgz={0!s}".format(waveformFilePath))
	# 		elif (waveformFileFormat == "fst"):
	# 			waveformFilePath = self.Directories.Working / (testbench.ModuleName + ".fst")
	# 			runOptions.append("--fst={0!s}".format(waveformFilePath))
	# 		elif (waveformFileFormat == "ghw"):
	# 			waveformFilePath = self.Directories.Working / (testbench.ModuleName + ".ghw")
	# 			runOptions.append("--wave={0!s}".format(waveformFilePath))
	# 		else:                                            raise SimulatorException("Unknown waveform file format for GHDL.")
	#
	# 	ghdl.Run(testbench.ModuleName, runOptions)
	
	def GetViewer(self):
		return self
	
	def View(self, testbench):
		self._LogNormal("Executing GTKWave...")

		# FIXME: get waveform database filename from testbench object
		waveformFileFormat =  self.Host.PoCConfig[testbench.ConfigSectionName]['ghdlWaveformFileFormat']
		if (waveformFileFormat == "vcd"):
			waveformFilePath = self.Directories.Working / (testbench.ModuleName + ".vcd")
		elif (waveformFileFormat == "vcdgz"):
			waveformFilePath = self.Directories.Working / (testbench.ModuleName + ".vcd.gz")
		elif (waveformFileFormat == "fst"):
			waveformFilePath = self.Directories.Working / (testbench.ModuleName + ".fst")
		elif (waveformFileFormat == "ghw"):
			waveformFilePath = self.Directories.Working / (testbench.ModuleName + ".ghw")
		else:                                            raise SimulatorException("Unknown waveform file format for GHDL.")
		
		if (not waveformFilePath.exists()):
			raise SkipableSimulatorException("Waveform file '{0!s}' not found.".format(waveformFilePath)) \
				from FileNotFoundError(str(waveformFilePath))
		
		gtkwBinaryPath =    self.Directories.GTKWBinary
		gtkwVersion =       self.Host.PoCConfig['INSTALL.GTKWave']['Version']
		gtkw = GTKWave(self.Host.Platform, gtkwBinaryPath, gtkwVersion)
		gtkw.Parameters[gtkw.SwitchDumpFile] = str(waveformFilePath)

		# if GTKWave savefile exists, load it's settings
		gtkwSaveFilePath =  self.Host.Directories.Root / self.Host.PoCConfig[testbench.ConfigSectionName]['gtkwSaveFile']
		if gtkwSaveFilePath.exists():
			self._LogDebug("Found waveform save file: '{0!s}'".format(gtkwSaveFilePath))
			gtkw.Parameters[gtkw.SwitchSaveFile] = str(gtkwSaveFilePath)
		else:
			self._LogDebug("Didn't find waveform save file: '{0!s}'".format(gtkwSaveFilePath))
		
		# run GTKWave GUI
		gtkw.View()
		
		# clean-up *.gtkw files
		if gtkwSaveFilePath.exists():
			self._LogNormal("  Cleaning up GTKWave save file...")
			removeKeys = ("[dumpfile]", "[savefile]")
			buffer = ""
			with gtkwSaveFilePath.open('r') as gtkwHandle:
				for lineNumber,line in enumerate(gtkwHandle):
					if (not line.startswith(removeKeys)):      buffer += line
					if (lineNumber > 10):                      break
				for line in gtkwHandle:
					buffer += line
			with gtkwSaveFilePath.open('w') as gtkwHandle:
				gtkwHandle.write(buffer)
