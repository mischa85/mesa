// SPDX-License-Identifier: MIT
// Archive only our authored vertex/fragment sources through public Metal APIs.
// This program creates no command queue and submits no GPU work.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <stdio.h>
#include <stdlib.h>

static void fail(NSString *operation, NSError *error)
{
   fprintf(stderr, "%s: %s\n", operation.UTF8String,
           error ? error.localizedDescription.UTF8String : "failed");
   exit(1);
}

int main(int argc, const char **argv)
{
   if (argc != 3) {
      fprintf(stderr, "usage: renderdump source.metal output.bin\n");
      return 1;
   }
   @autoreleasepool {
      NSError *error = nil;
      NSString *source = [NSString stringWithContentsOfFile:@(argv[1])
                                 encoding:NSUTF8StringEncoding error:&error];
      if (!source) fail(@"read authored source", error);
      id<MTLDevice> device = MTLCreateSystemDefaultDevice();
      if (!device) fail(@"create Metal device", nil);
      MTLCompileOptions *options = [MTLCompileOptions new];
      options.fastMathEnabled = YES; // Match the completed compute sweep.
      id<MTLLibrary> library = [device newLibraryWithSource:source options:options error:&error];
      if (!library) fail(@"compile authored source", error);
      id<MTLFunction> vertex = [library newFunctionWithName:@"v"];
      id<MTLFunction> fragment = [library newFunctionWithName:@"f"];
      if (!vertex || !fragment) fail(@"find v and f", nil);
      MTLRenderPipelineDescriptor *desc = [MTLRenderPipelineDescriptor new];
      desc.vertexFunction = vertex;
      desc.fragmentFunction = fragment;
      desc.rasterSampleCount = 1;
      desc.colorAttachments[0].pixelFormat = MTLPixelFormatRGBA32Float;
      id<MTLRenderPipelineState> pipeline =
         [device newRenderPipelineStateWithDescriptor:desc error:&error];
      if (!pipeline) fail(@"create render pipeline", error);
      MTLBinaryArchiveDescriptor *archiveDesc = [MTLBinaryArchiveDescriptor new];
      id<MTLBinaryArchive> archive = [device newBinaryArchiveWithDescriptor:archiveDesc error:&error];
      if (!archive) fail(@"create archive", error);
      if (![archive addRenderPipelineFunctionsWithDescriptor:desc error:&error])
         fail(@"add render pipeline", error);
      if (![archive serializeToURL:[NSURL fileURLWithPath:@(argv[2])] error:&error])
         fail(@"serialize archive", error);
      fprintf(stderr, "device=%s vertex=v fragment=f color=RGBA32Float samples=1\n",
              device.name.UTF8String);
   }
   return 0;
}
