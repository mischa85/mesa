#ifndef SPILL_CENSUS_H
#define SPILL_CENSUS_H
#include "agx_apple9_ir.h"
#include "agx_compiler.h"
#include "util/hash_table.h"
struct sc_tag { unsigned kind, op, uniform, cheap; };
extern _Thread_local struct hash_table *sc_common, *sc_physical;
extern _Thread_local void *sc_mem;
extern _Thread_local struct sc_tag sc_current;
FILE *spill_census_log(void);
static inline void sc_put(struct hash_table *h, const void *key, struct sc_tag t) {
 if (!h) return;
 struct sc_tag *v = ralloc(sc_mem, struct sc_tag); *v=t;
 _mesa_hash_table_insert(h,key,v);
}
static inline struct sc_tag sc_get(struct hash_table *h, const void *key) {
 struct hash_entry *e=h?_mesa_hash_table_search(h,key):NULL;
 return e?*(struct sc_tag *)e->data:(struct sc_tag){0};
}
#endif
