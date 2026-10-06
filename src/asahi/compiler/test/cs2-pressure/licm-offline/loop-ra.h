void latency_demand_begin(agx_context *ctx);
void latency_demand_end(void);
void latency_demand(unsigned block,unsigned n);
/* Private offline instrumentation; all register demand is in 16-bit units. */
extern FILE *latency_log(void);
static _Thread_local bool latency_record;
static _Thread_local unsigned *latency_demands;
static _Thread_local unsigned latency_num_blocks;
struct latency_candidate { void *key; unsigned *peak; unsigned count; struct latency_candidate *next; };
static _Thread_local struct latency_candidate *latency_candidates;
void latency_demand_begin(agx_context *ctx) {
 latency_record=ctx->ra_target.defer_spill_lowering;
 if(!latency_record)return;
 free(latency_demands); latency_num_blocks=0;
 agx_foreach_block(ctx,b) latency_num_blocks=MAX2(latency_num_blocks,b->index+1);
 latency_demands=calloc(latency_num_blocks,sizeof(unsigned));
}
void latency_demand_end(void) { latency_record=false; }
void latency_demand(unsigned block,unsigned n) {
 if(latency_record) { assert(block<latency_num_blocks); latency_demands[block]=MAX2(latency_demands[block],n); }
}
static void latency_save(struct apple9_shared_ra *ra,void *key) {
 unsigned count=0;
 for(struct agx_apple9_block *b=ra->program->blocks;b;b=b->next)
  for(nir_cf_node *n=b->nir?b->nir->cf_node.parent:NULL;n;n=n->parent)
   if(n->type==nir_cf_node_loop)count=MAX2(count,nir_loop_first_block(nir_cf_node_as_loop(n))->index+1);
 struct latency_candidate *c=calloc(1,sizeof(*c));c->key=key;c->count=count;c->peak=calloc(count,sizeof(unsigned));
 for(struct agx_apple9_block *b=ra->program->blocks;b;b=b->next) {
  agx_block *common=ra->blocks[b->index]; if(!common)continue;
  assert(common->index<latency_num_blocks);
  for(nir_cf_node *n=b->nir?b->nir->cf_node.parent:NULL;n;n=n->parent)if(n->type==nir_cf_node_loop) {
   unsigned h=nir_loop_first_block(nir_cf_node_as_loop(n))->index;
   c->peak[h]=MAX2(c->peak[h],latency_demands[common->index]);
  }
 }
 c->next=latency_candidates;latency_candidates=c;
}
static void latency_dump(void *key) {
 bool found=false;
 for(struct latency_candidate *c=latency_candidates;c;c=c->next)if(c->key==key&&!found) {
  found=true;for(unsigned i=0;i<c->count;i++)if(c->peak[i])fprintf(latency_log(),"LOOP_PEAK header=%u half=%u\n",i,c->peak[i]);
 }
 assert(found);
 while(latency_candidates) {struct latency_candidate *c=latency_candidates;latency_candidates=c->next;free(c->peak);free(c);}
 free(latency_demands);latency_demands=NULL;
}
