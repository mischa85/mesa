static unsigned latency_depth(nir_block *block) {
 unsigned depth=0;for(nir_cf_node *n=block?block->cf_node.parent:NULL;n;n=n->parent)depth+=n->type==nir_cf_node_loop;return depth;
}
static void latency_loop_ids(nir_block *block) {
 fprintf(apple9_log()," loops=");bool first=true;
 for(nir_cf_node *n=block?block->cf_node.parent:NULL;n;n=n->parent)if(n->type==nir_cf_node_loop) {
  fprintf(apple9_log(),"%s%u",first?"":",",nir_loop_first_block(nir_cf_node_as_loop(n))->index);first=false;
 }
 if(first)fprintf(apple9_log(),"-");
}
static void latency_nir(nir_shader *nir) {
 nir_foreach_block(b,nir_shader_get_entrypoint(nir))nir_foreach_instr(I,b) {
  if(I->type!=nir_instr_type_alu)continue;
  fprintf(apple9_log(),"LOOP_NIR op=%s",nir_op_infos[nir_instr_as_alu(I)->op].name);latency_loop_ids(b);fprintf(apple9_log(),"\n");
 }
}
static void latency_physical(const struct agx_apple9_vir_program *p) {
 fprintf(apple9_log(),"LATENCY_BEGIN peak=%u pre_spill=%u\n",p->peak_live_gprs,p->pre_spill_gprs);
 for(unsigned i=0;i<p->instruction_count;i++) {
  const struct agx_apple9_vir_instr *I=p->instructions[i];const struct agx_apple9_block *b=agx_apple9_instr_block(I);
  fprintf(apple9_log(),"LATENCY_INS i=%u block=%u depth=%u op=%u",i,b?b->index:~0u,latency_depth(b?b->nir:NULL),I->op);
  latency_loop_ids(b?b->nir:NULL);fprintf(apple9_log(),"\n");
 }
}
struct latency_origin {nir_instr *I;nir_loop *loop;unsigned header;};
static void latency_hoist(nir_shader *nir,bool enabled) {
 struct util_dynarray origins=UTIL_DYNARRAY_INIT;
 nir_index_blocks(nir_shader_get_entrypoint(nir));
 nir_foreach_block(b,nir_shader_get_entrypoint(nir)) {
  for(nir_cf_node *n=b->cf_node.parent;n;n=n->parent)if(n->type==nir_cf_node_loop) {
   nir_loop *loop=nir_cf_node_as_loop(n);
   if(b==nir_loop_first_block(loop))fprintf(apple9_log(),"LOOP_META header=%u depth=%u\n",b->index,latency_depth(b));
   if(enabled)nir_foreach_instr(I,b)if(I->type==nir_instr_type_alu) {
    struct latency_origin v={I,loop,nir_loop_first_block(loop)->index};util_dynarray_append(&origins,v);
   }
  }
 }
 if(enabled)agx_nir_opt_apple9_licm(nir);
 util_dynarray_foreach(&origins,struct latency_origin,o) {
  bool inside=false;
  for(nir_cf_node *n=o->I->block->cf_node.parent;n;n=n->parent)inside|=n==&o->loop->cf_node;
  if(!inside) {nir_alu_instr *a=nir_instr_as_alu(o->I);fprintf(apple9_log(),"LOOP_HOIST header=%u op=%s words=%u\n",o->header,nir_op_infos[a->op].name,DIV_ROUND_UP(a->def.num_components*a->def.bit_size,32));}
 }
 util_dynarray_fini(&origins);
}
