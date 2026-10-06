/* SPDX-License-Identifier: MIT
 * Offline experiment: reject intra-block schedules whose NIR word-pressure
 * peak exceeds the original schedule. This is not a physical-register bound.
 */
struct corpus_word_pressure {
   unsigned *width;
   BITSET_WORD *live;
   unsigned demand;
};

static bool
corpus_record_width(nir_def *def, void *data)
{
   unsigned *width = data;
   width[def->index] = def->num_components * DIV_ROUND_UP(def->bit_size, 32);
   return true;
}

static bool
corpus_add_live(nir_src *src, void *data)
{
   struct corpus_word_pressure *s = data;
   if (!nir_src_is_undef(*src) && !BITSET_TEST(s->live, src->ssa->index)) {
      BITSET_SET(s->live, src->ssa->index);
      s->demand += s->width[src->ssa->index];
   }
   return true;
}

static bool
corpus_kill_live(nir_def *def, void *data)
{
   struct corpus_word_pressure *s = data;
   if (BITSET_TEST(s->live, def->index)) {
      BITSET_CLEAR(s->live, def->index);
      s->demand -= s->width[def->index];
   }
   return true;
}

static unsigned
corpus_schedule_pressure(nir_block *block, nir_instr **order, unsigned count,
                         unsigned *width, BITSET_WORD *live, unsigned words)
{
   memset(live, 0, words * sizeof(*live));
   struct corpus_word_pressure s = {.width = width, .live = live};
   U_SPARSE_BITSET_FOREACH_SET(&block->live_out, id) {
      BITSET_SET(live, id);
      s.demand += width[id];
   }
   nir_if *following = nir_block_get_following_if(block);
   if (following)
      corpus_add_live(&following->condition, &s);
   unsigned peak = s.demand;
   while (count) {
      nir_instr *instr = order[--count];
      nir_foreach_def(instr, corpus_kill_live, &s);
      nir_foreach_src(instr, corpus_add_live, &s);
      peak = MAX2(peak, s.demand);
   }
   return peak;
}
