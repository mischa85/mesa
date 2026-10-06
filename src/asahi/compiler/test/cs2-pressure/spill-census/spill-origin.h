/* kind: 0 coupling/untracked, 1 arithmetic, 2 constant, 3 uniform import,
 * 4 texture result, 5 memory result, 6 phi, 7 loop-header phi, 8 system value. */
static struct sc_tag *sc_origins(agx_context *ctx) {
 struct sc_tag *a=calloc(ctx->alloc,sizeof(*a));
 agx_foreach_block(ctx,b) agx_foreach_instr_in_block(b,I) {
  struct sc_tag t={.kind=1};
  if(I->op==AGX_OPCODE_MOV_IMM)t=(struct sc_tag){.kind=2,.uniform=1,.cheap=1};
  else if(I->op==AGX_OPCODE_PHI)t.kind=b->loop_header?7:6;
  else if(I->op==AGX_OPCODE_GET_SR)t.kind=8;
  else if((I->op==AGX_OPCODE_APPLE9 || I->op==AGX_OPCODE_APPLE9_PURE) && I->apple9) {
   t.op=I->apple9->op;
   switch(I->apple9->op) {
   case AGX_APPLE9_VIR_IOR_UNIFORM:t.kind=3;break;
   case AGX_APPLE9_VIR_TEXTURE_SAMPLE:t.kind=4;break;
   case AGX_APPLE9_VIR_DEVICE_LOAD:case AGX_APPLE9_VIR_SHARED_LOAD:
   case AGX_APPLE9_VIR_PRIVATE_LOAD:case AGX_APPLE9_VIR_TILE_LOAD:t.kind=5;break;
   case AGX_APPLE9_VIR_GET_SR:case AGX_APPLE9_VIR_GET_GLOBAL_ID:t.kind=8;break;
   default:break;
   }
   t.cheap=I->nr_srcs==0 && I->nr_dests==1 &&
      agx_apple9_instr_is_pure_alu(I->apple9);
   t.uniform |= t.cheap;
  }
  agx_foreach_ssa_dest(I,d) a[I->dest[d].value]=t;
 }
 bool progress; unsigned passes=0;
 do {
  if(++passes>256) {fprintf(stderr,"ERROR sc_origins nonconvergence alloc=%u\n",ctx->alloc);abort();}
  progress=false;
  agx_foreach_instr_global(ctx,I) {
   if ((I->op==AGX_OPCODE_SPLIT || I->op==AGX_OPCODE_MOV) &&
       I->nr_srcs==1 && I->src[0].type==AGX_INDEX_NORMAL) {
    agx_foreach_ssa_dest(I,d) {
     struct sc_tag *v=&a[I->dest[d].value],t=a[I->src[0].value];
     if(memcmp(v,&t,sizeof(t))){*v=t;progress=true;}
    }
   } else if(((I->op==AGX_OPCODE_APPLE9 || I->op==AGX_OPCODE_APPLE9_PURE) && I->apple9 && agx_apple9_instr_is_pure_alu(I->apple9)) ||
             I->op==AGX_OPCODE_COLLECT || I->op==AGX_OPCODE_PHI) {
    bool uniform=I->nr_srcs>0;
    agx_foreach_src(I,s) uniform &= I->src[s].type==AGX_INDEX_IMMEDIATE ||
       (I->src[s].type==AGX_INDEX_NORMAL && a[I->src[s].value].uniform);
    if(uniform) agx_foreach_ssa_dest(I,d) {
     if(!a[I->dest[d].value].uniform){a[I->dest[d].value].uniform=1;progress=true;}
    }
   }
  }
 } while(progress);
 return a;
}
static void sc_spill_moves(agx_context *ctx, struct sc_tag *a, unsigned n) {
 agx_foreach_instr_global(ctx,I) {
  if(I->op!=AGX_OPCODE_MOV || (!I->dest[0].memory && !I->src[0].memory))continue;
  agx_index x=I->dest[0].memory?I->dest[0]:I->src[0];
  if(x.value>=n && x.value<2*n)sc_put(sc_common,I,a[x.value-n]);
 }
 free(a);
}
