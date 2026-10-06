#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build a private CTS extractor with bounded chunks and lossless chunk outputs.
Never modifies the shared CTS checkout. Run after its vk-build-programs build.
"""
from pathlib import Path
import argparse,json,shlex,subprocess
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);d=a.output.resolve();b=a.build.resolve();source=a.source.resolve()/'external/vulkancts/modules/vulkan/vktBuildPrograms.cpp';s='#include "deSha1.h"\n'+source.read_text()
s=s.replace('const uint32_t numThreads    = deGetNumAvailableLogicalCores();','const uint32_t numThreads    = 2;').replace('const size_t numNodesInChunk = 500000;','const size_t numNodesInChunk = 4000;\n    unsigned corpusChunk = 0;')
# The unmodified writer deletes shaders not present in the current chunk.
# Give every chunk an independent registry to preserve the full population.
s=s.replace('vk::BinaryRegistryWriter registryWriter(dstPath);','const std::string chunkPath = dstPath + "/chunk-" + de::toString(corpusChunk++);\n            vk::BinaryRegistryWriter registryWriter(chunkPath);')
s=s.replace('if (progIter->buildStatus == Program::STATUS_PASSED)', 'if (progIter->buildStatus == Program::STATUS_PASSED && progIter->validationStatus != Program::STATUS_FAILED)')
s=s.replace('                    notSupported++;', '                    tcu::print("CORPUS_INIT_SKIP %s\\n", casePath.c_str());\n                    notSupported++;')
# Preserve names before hashing/deduplicating the binary registries.
s=s.replace('registryWriter.addProgram(progIter->id, *progIter->binary);','''{
                    registryWriter.addProgram(progIter->id, *progIter->binary);
                    deSha1 digest; char hex[41];
                    deSha1_compute(&digest, progIter->binary->getSize(), progIter->binary->getBinary());
                    deSha1_render(&digest, hex); hex[40] = 0;
                    std::cout << "CORPUS_PROGRAM " << (corpusChunk - 1) << " " << hex << " "
                              << progIter->id.testCasePath << " " << progIter->id.programName << "\\n";
                }''')
# Avoid large per-shader logs on successful compilation; failed diagnostics remain.
f=d/'vktBuildPrograms.cpp';f.write_text(s)
commands=subprocess.check_output(['ninja','-t','commands','vk-build-programs'],cwd=b,text=True).splitlines();entry=next(c for c in commands if 'vktBuildPrograms.cpp.o ' in c or 'vktBuildPrograms.cpp.o -c' in c)
args=shlex.split(entry);cmd=[];skip=False
for x in args:
 if skip:skip=False;continue
 if x in ['-o','-MF','-MT']:skip=True;continue
 if x in ['-MD','-MMD'] or x.endswith('/vktBuildPrograms.cpp'):continue
 cmd.append(x)
obj=d/'vktBuildPrograms.cpp.o';cmd += [str(f),'-o',str(obj)];subprocess.run(cmd,cwd=b,check=True)
# CMake wraps the final link command in ':'; run only the actual compiler argv.
link=shlex.split(commands[-1]);start=next(i for i,x in enumerate(link) if x.endswith(('/c++','/g++')));link=link[start:];link=link[:link.index('&&')] if '&&' in link else link
for i,x in enumerate(link):
 if x.endswith('vktBuildPrograms.cpp.o'):link[i]=str(obj)
 if i and link[i-1]=='-o':link[i]=str(d/'vk-build-programs')
subprocess.run(link,cwd=b,check=True);(d/'commands.json').write_text(json.dumps(dict(compile=cmd,link=link),indent=2)+'\n')
