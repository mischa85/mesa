_Thread_local struct hash_table *sc_common, *sc_physical;
_Thread_local void *sc_mem;
_Thread_local struct sc_tag sc_current;
static void sc_begin(void) {
 sc_mem=ralloc_context(NULL);sc_common=_mesa_pointer_hash_table_create(sc_mem);
 sc_physical=_mesa_pointer_hash_table_create(sc_mem);
}
static unsigned sc_depth(const struct agx_apple9_vir_instr *I) {
 const struct agx_apple9_block *b=agx_apple9_instr_block(I);
 unsigned d=0;
 for(nir_cf_node *n=b&&b->nir?b->nir->cf_node.parent:NULL;n;n=n->parent)
  d+=n->type==nir_cf_node_loop;
 return d;
}
static void sc_dump(const struct agx_apple9_vir_program *p,unsigned stage) {
 fprintf(spill_census_log(),"SPILL_CENSUS stage=%u gprs=%u\n",stage,p->peak_live_gprs);
 for(unsigned i=0;i<p->instruction_count;i++) {
  const struct agx_apple9_vir_instr *I=p->instructions[i];
  if(I->op!=AGX_APPLE9_VIR_SPILL_STORE && I->op!=AGX_APPLE9_VIR_SPILL_LOAD)continue;
  struct sc_tag t=sc_get(sc_physical,I);
  unsigned before=999999,after=999999;
  for(unsigned j=i;j>0;j--) {
   if(agx_apple9_instr_block(p->instructions[j-1])!=agx_apple9_instr_block(I))break;
   if(p->instructions[j-1]->op==AGX_APPLE9_VIR_TEXTURE_SAMPLE){before=i-j+1;break;}
  }
  for(unsigned j=i+1;j<p->instruction_count;j++) {
   if(agx_apple9_instr_block(p->instructions[j])!=agx_apple9_instr_block(I))break;
   if(p->instructions[j]->op==AGX_APPLE9_VIR_TEXTURE_SAMPLE){after=j-i;break;}
  }
  fprintf(spill_census_log(),"SPILL_ITEM save=%u kind=%u op=%u uniform=%u cheap=%u depth=%u before=%u after=%u\n",
   I->op==AGX_APPLE9_VIR_SPILL_STORE,t.kind,t.op,t.uniform,t.cheap,sc_depth(I),before,after);
 }
 fprintf(spill_census_log(),"SPILL_CENSUS_END\n");
 ralloc_free(sc_mem);sc_mem=NULL;sc_common=sc_physical=NULL;
}
