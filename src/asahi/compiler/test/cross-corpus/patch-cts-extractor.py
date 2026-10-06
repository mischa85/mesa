#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build a private CTS extractor with bounded chunks and lossless chunk outputs.
Never modifies the shared CTS checkout. Run after its vk-build-programs build.
"""
from pathlib import Path
import argparse,json,shlex,subprocess
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);d=a.output.resolve();b=a.build.resolve();source=a.source.resolve()/'external/vulkancts/modules/vulkan/vktBuildPrograms.cpp';s='#include "deSha1.h"\n'+source.read_text()
s=s.replace('const uint32_t numThreads    = deGetNumAvailableLogicalCores();','const uint32_t numThreads    = 2;').replace('const size_t numNodesInChunk = 500000;','const size_t numNodesInChunk = 4000;\n    unsigned corpusChunk = 0;')
# Stream one binary per distinct chunk hash; no binary registry is written.
s=s.replace('vk::BinaryRegistryWriter registryWriter(dstPath);', 'std::set<std::string> emitted;')
s='#include <set>\n#include <cstdlib>\n'+s
s=s.replace('    unsigned corpusChunk = 0;', '    unsigned corpusChunk = 0;\n    const unsigned resumeChunk = getenv("CORPUS_RESUME_CHUNK") ? atoi(getenv("CORPUS_RESUME_CHUNK")) : 0;')
s=s.replace('                numNodesAdded++;', '                numNodesAdded++;\n                if (corpusChunk < resumeChunk) { iterator.next(); continue; }')
s=s.replace('if (progIter->buildStatus == Program::STATUS_PASSED)', 'if (progIter->buildStatus == Program::STATUS_PASSED && progIter->validationStatus != Program::STATUS_FAILED)')
s=s.replace('                    notSupported++;', '                    tcu::print("CORPUS_INIT_SKIP %s\\n", casePath.c_str());\n                    notSupported++;')
s=s.replace('registryWriter.addProgram(progIter->id, *progIter->binary);', '''{
                    deSha1 digest; char hex[41];
                    deSha1_compute(&digest, progIter->binary->getSize(), progIter->binary->getBinary());
                    deSha1_render(&digest, hex); hex[40] = 0;
                    if (emitted.insert(hex).second) {
                        const unsigned char *bytes = progIter->binary->getBinary();
                        std::string data; data.reserve(progIter->binary->getSize()*2);
                        static const char digits[] = "0123456789abcdef";
                        for (size_t i=0;i<progIter->binary->getSize();i++) {
                            data += digits[bytes[i] >> 4]; data += digits[bytes[i] & 15];
                        }
                        std::cout << "CORPUS_BINARY " << hex << " " << data << "\\n";
                    }
                    std::cout << "CORPUS_PROGRAM " << corpusChunk << " " << hex << " "
                              << progIter->id.testCasePath << " " << progIter->id.programName << "\\n";
                }''')
s=s.replace('            registryWriter.write();', '            if (corpusChunk >= resumeChunk) std::cout << "CORPUS_CHUNK_DONE " << corpusChunk << std::endl;\n            corpusChunk++;')
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
