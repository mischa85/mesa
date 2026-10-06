#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Classify observed failures with physical-device and compiler evidence.

Keeps an unclassified bucket instead of guessing that an unknown failure is
unsupported. Does not change the compiler or rewrite original replay rows.
"""
import argparse, collections, gzip, io, json, re, subprocess, xml.etree.ElementTree as ET
from pathlib import Path
from packed import Pack, results

p = argparse.ArgumentParser()
p.add_argument('--pack', type=Path, required=True)
p.add_argument('--population', required=True)
p.add_argument('--baseline', type=Path, required=True)
p.add_argument('--caps', type=Path, required=True)
p.add_argument('--registry', type=Path, required=True)
p.add_argument('--runs', type=Path, nargs='+', required=True)
p.add_argument('--include-crashes', action='store_true')
p.add_argument('--replace', action='store_true', help='Reclassify an existing audit from the same evidence')
a = p.parse_args()
pack = Pack(a.pack, writable=True)
db = pack.db
caps = json.loads(a.caps.read_text())
extensions = set(caps['extensions'])
requirements = {node.attrib['name']: [dict(x.attrib) for x in node.findall('enable')]
                for node in ET.parse(a.registry).findall('./spirvcapabilities/spirvcapability')}
failure_statuses = {'compiler_failure', 'crash'} if a.include_crashes else {'compiler_failure'}
expected = {r['key'] for r in results(a.baseline) if r['status'] in failure_statuses}
observed = {}
run_paths = {json.loads((run/'provenance.json').read_text())['population']: str(run)
             for run in a.runs}
for run in a.runs:
    for row in results(run):
        assert row['key'] not in observed, row['key']
        observed[row['key']] = row
assert observed.keys() == expected
db.executescript('''
CREATE TABLE IF NOT EXISTS failure_audit(
 population TEXT,key TEXT,sha TEXT,stage INTEGER,category TEXT,cause TEXT,
 reason TEXT,triggers TEXT,evidence TEXT,source TEXT,
 PRIMARY KEY(population,key)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS failure_capabilities(
 population TEXT,key TEXT,capability TEXT,requirements TEXT,
 PRIMARY KEY(population,key,capability)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS failure_groups(
 population TEXT,sha TEXT,test_group TEXT,
 PRIMARY KEY(population,sha,test_group)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS reports(name TEXT PRIMARY KEY,data TEXT) WITHOUT ROWID;
''')
assert a.replace or not db.execute('SELECT 1 FROM reports WHERE name=?', ('failure-audit-' + a.population,)).fetchone()
counts = collections.Counter()
review = []

# Match the enums from the compiler checkout, rather than baking numeric
# opcode/encoding identities into an audit that will be reused later.
compiler = Path(__file__).resolve().parents[2]
def enum_value(header, enum, name, prefix):
    body = (compiler / header).read_text().split('enum ' + enum + ' {', 1)[1].split('};', 1)[0]
    before = body.split(name, 1)[0]
    assert '=' not in before, 'Explicit enum values need an updated reader'
    return len(re.findall(r'\b' + prefix + r'\w+', before))
publication_op = enum_value('agx_apple9_ir.h', 'agx_apple9_vir_opcode',
                            'AGX_APPLE9_VIR_PUBLICATION_TUPLE', 'AGX_APPLE9_VIR_')
grad_volume_encoding = enum_value('agx_apple9_machine.h', 'agx_apple9_encoding',
                                  'AGX_APPLE9_ENC_TEXTURE_GRAD_VOLUME_PARAMS', 'AGX_APPLE9_ENC_')

def user_output_spans(dis):
    """Count occupied user output locations, including nested interface blocks."""
    types = {name: (op, args.split()) for name, op, args in
             re.findall(r'(%\w+) = OpType(\w+)([^\n]*)', dis)}
    constants = {name: int(value) for name, value in
                 re.findall(r'(%\w+) = OpConstant %\w+ (\d+)\s*\n', dis)}
    def slots(name):
        op, args = types[name]
        if op in ('Int', 'Float', 'Bool'):
            return 1
        if op == 'Vector':
            width = int(types[args[0]][1][0])
            return (width * int(args[1]) + 127) // 128
        if op == 'Matrix':
            return slots(args[0]) * int(args[1])
        if op == 'Array':
            return slots(args[0]) * constants[args[1]]
        if op == 'Struct':
            return sum(slots(x) for x in args)
        raise ValueError((name, op, args))
    variables = dict(re.findall(r'(%\w+) = OpVariable (%\w+) Output', dis))
    locations = [(var, int(loc)) for var, loc in
                 re.findall(r'OpDecorate (%\w+) Location (\d+)', dis) if var in variables]
    return [(loc, slots(types[variables[var]][1][1])) for var, loc in locations]

for key, row in observed.items():
    assert row['status'] in failure_statuses, (key, row['status'])
    sha = key.split('-')[0]
    source = db.execute('SELECT source FROM modules WHERE sha=?', (sha,)).fetchone()[0]
    lines = row['diagnostics']
    diagnostic = '\n'.join(lines)
    rejected = list(dict.fromkeys(re.findall(
        r'(?:Unsupported|Unimplemented) SPIR-V capability: SpvCapability(\w+)', diagnostic)))
    unimplemented = re.findall(r'Unimplemented SPIR-V capability: SpvCapability(\w+)', diagnostic)
    # Unimplemented is not itself proof of an unadvertised device feature.
    # Verify its registry extension prerequisite against the queried device.
    for cap in unimplemented:
        reqs = requirements.get(cap, [])
        assert reqs and all(x.get('requires', x.get('extension', '')).startswith('VK_') and
                            x.get('requires', x.get('extension')) not in extensions for x in reqs), (cap, reqs)
    reasons = [line.removeprefix('CORPUS_REASON ') for line in lines
               if line.startswith('CORPUS_REASON ')]
    triggers = [line.removeprefix('CORPUS_TRIGGER ') for line in lines
                if line.startswith('CORPUS_TRIGGER ')]
    reason = reasons[-1] if reasons else '\n'.join(lines)
    evidence = dict(diagnostic_run=run_paths[row['population']], outcome=row['status'])
    category, cause = 'unclassified', reason
    if rejected:
        category, cause = 'unadvertised_feature', 'SPIR-V capability: ' + rejected[0]
        evidence['rejected_capabilities'] = rejected
        evidence['basis'] = 'Physical-device capability warning, or unimplemented capability with absent required extension'
    elif unsupported := re.search(r'Unsupported extension: (SPV_AMD_shader_\w+)', diagnostic):
        cause = unsupported[1]
        assert cause.replace('SPV_', 'VK_', 1) not in extensions
        category = 'unadvertised_feature'
    elif '.ssbo.unsized_array_length.' in source and 'length64' in source:
        assert 'VK_EXT_shader_64bit_indexing' not in extensions
        category, cause = 'unadvertised_feature', '64-bit buffer array length'
        evidence['cts_support_check'] = 'vktSSBOLayoutTests.cpp: shader64BitIndexing requirement'
    elif '.atomic_operations.exchange_float16_' in source:
        # This SPIR-V instruction uses Float16, without a distinct atomic
        # capability. The CTS support check requires these extra feature bits.
        assert not caps['shaderBufferFloat16Atomics'] and not caps['shaderSharedFloat16Atomics']
        category, cause = 'unadvertised_feature', 'float16 atomic exchange'
        evidence.update(shaderBufferFloat16Atomics=0, shaderSharedFloat16Atomics=0,
                        cts_support_check='vktAtomicOperationTests.cpp: AtomicOperationCase::checkSupport')
    elif '.atomic_operations.add_float32_compute_shared/' in source:
        assert not caps['shaderSharedFloat32AtomicAdd']
        category, cause = 'unadvertised_feature', 'float32 shared atomic add'
        evidence.update(shaderSharedFloat32AtomicAdd=0,
                        cts_support_check='vktAtomicOperationTests.cpp: AtomicOperationCase::checkSupport')
    elif '.limits.near_max.fragment_input.components_' in source:
        needed = int(re.search(r'components_(\d+)', source)[1])
        limit = min(caps['maxVertexOutputComponents'], caps['maxFragmentInputComponents'])
        assert needed > limit
        category, cause = 'exceeds_advertised_limit', 'stage I/O components'
        evidence.update(required_components=needed, advertised_components=limit)
    elif '.workgroup_memory_explicit_layout.size.' in source:
        needed = int(source.split('.size.')[1].split('/')[0])
        assert needed > caps['maxComputeSharedMemorySize']
        category, cause = 'exceeds_advertised_limit', 'workgroup shared memory'
        evidence.update(required_bytes=needed, advertised_bytes=caps['maxComputeSharedMemorySize'])
    elif reason == 'Apple9 render requires FP32 color outputs and standard single-source blending':
        dis = subprocess.check_output(['spirv-dis', '--no-color', '-'], input=pack.blob(sha)).decode()
        output_ids = set(re.findall(r'(%\w+) = OpVariable %\w+ Output', dis))
        output_locations = [int(location) for var, location in
                            re.findall(r'OpDecorate (%\w+) Location (\d+)', dis) if var in output_ids]
        if output_locations and max(output_locations) >= caps['maxFragmentOutputAttachments']:
            category, cause = 'exceeds_advertised_limit', 'color attachment locations'
            evidence.update(output_locations=output_locations,
                            maxColorAttachments=caps['maxColorAttachments'])
            pack.add_file('audit/' + a.population + '/' + sha + '.spvasm', dis.encode())
    if category == 'unclassified':
        dis = subprocess.check_output(['spirv-dis', '--no-color', '-'], input=pack.blob(sha)).decode()
        pack_failures = re.findall(rf'APPLE9_PACK_FAIL .*op={publication_op} enc={grad_volume_encoding} dst=p(\d+) .*comps=16 ', diagnostic)
        if (pack_failures and all(int(base) + 16 > 32 for base in pack_failures)
                and set(re.findall(r'OpCapability (\w+)', dis)) == {'Shader'}
                and '.image_robustness.' in source):
            assert caps['robustImageAccess']
            category, cause = 'advertised_backend_failure', '3D texture-gradient publication exceeds its encodable window'
            evidence.update(publication_bases=[int(x) for x in pack_failures],
                            publication_width=16, encoding_limit=32,
                            encoding='AGX_APPLE9_ENC_TEXTURE_GRAD_VOLUME_PARAMS',
                            packer_check='agx_apple9_ir.c: PUBLICATION_TUPLE base <= 32 - components',
                            robustImageAccess=caps['robustImageAccess'])
            triggers.extend(line for line in lines if line.startswith('APPLE9_PACK_FAIL '))
        elif 'OpCapability UntypedPointersKHR' in dis:
            assert 'VK_KHR_shader_untyped_pointers' not in extensions
            category, cause = 'unadvertised_feature', 'untyped pointers'
        elif 'OpCapability DescriptorHeapEXT' in dis:
            assert 'VK_EXT_descriptor_heap' not in extensions
            category, cause = 'unadvertised_feature', 'descriptor heap'
        elif '.transform_feedback.' in source:
            streams = [int(x) for x in re.findall(r'Op(?:Member)?Decorate %\w+(?: \d+)? Stream (\d+)', dis)]
            locations = user_output_spans(dis)
            required = max((loc + width for loc, width in locations), default=0) * 4
            limit = caps['maxGeometryOutputComponents' if row['stage'] == 3 else 'maxVertexOutputComponents']
            if streams and max(streams) >= caps['maxTransformFeedbackStreams']:
                category, cause = 'exceeds_advertised_limit', 'geometry output stream index'
                evidence.update(output_streams=streams, maxTransformFeedbackStreams=caps['maxTransformFeedbackStreams'])
            elif required > limit:
                category, cause = 'exceeds_advertised_limit', 'stage output components'
                evidence.update(required_user_components=required, advertised_components=limit,
                                cts_support_check='vktTransformFeedbackFuzzLayoutCase.cpp: locationsRequired * 4 + 7')
        pack.add_file('audit/' + a.population + '/' + sha + '.spvasm', dis.encode())
    if category == 'unclassified':
        review.append(dict(key=key, reason=reason, source=source))
    counts[category] += 1
    db.execute('INSERT OR REPLACE INTO failure_audit VALUES(?,?,?,?,?,?,?,?,?,?)',
               (a.population, key, sha, row['stage'], category, cause, reason,
                json.dumps(triggers), json.dumps(evidence), source))
    db.executemany('INSERT OR REPLACE INTO failure_capabilities VALUES(?,?,?,?)',
                   [(a.population, key, cap, json.dumps(requirements.get(cap, []))) for cap in rejected])
db.commit()

# Map every observed CTS alias, not just the first canonical source. Keep
# unique module/group pairs; raw test/program aliases already live in the pack.
shas = {key.split('-')[0] for key in expected}
groups = set()
def consume(stream):
    for line in stream:
        if not line.strip():
            continue
        row = json.loads(line)
        if row['sha256'] in shas:
            groups.add((row['sha256'], '.'.join(row['testcase'].split('.')[:4])))

consume(gzip.GzipFile(fileobj=io.BytesIO(pack.file('vulkan-cts/aliases.jsonl.gz'))))
for path, in db.execute("SELECT path FROM files WHERE path LIKE 'extraction/aliases-%' ORDER BY path").fetchall():
    consume(io.BytesIO(pack.file(path)))
db.executemany('INSERT OR IGNORE INTO failure_groups VALUES(?,?,?)',
               [(a.population, sha, group) for sha, group in sorted(groups)])
summary = dict(population=a.population, failures=len(observed),
               unique_modules=len(shas), categories=dict(counts), unclassified=review,
               outcomes=dict(collections.Counter(row['status'] for row in observed.values())),
               scope='Offline shader compilation, not CTS execution or runtime checkSupport',
               advertised_backend_ranking=[dict(cause=c, modules=n)
                    for c,n in db.execute('''SELECT cause,count(DISTINCT sha)
                        FROM failure_audit WHERE population=? AND category='advertised_backend_failure'
                        GROUP BY cause ORDER BY count(DISTINCT sha) DESC''', (a.population,))],
               stage_categories=[dict(stage=s, category=c, entries=n, modules=m)
                                 for s,c,n,m in db.execute('''SELECT stage,category,count(*),count(DISTINCT sha)
                                     FROM failure_audit WHERE population=? GROUP BY stage,category''', (a.population,))],
               causes=[dict(category=c, cause=r, entries=n, modules=m)
                       for c,r,n,m in db.execute('''SELECT category,cause,count(*),count(DISTINCT sha)
                           FROM failure_audit WHERE population=? GROUP BY category,cause ORDER BY count(*) DESC''', (a.population,))],
               note='Whole-population replay includes CTS programs whose runtime checkSupport would skip on this device. Unclassified rows must be reviewed before a backend ranking can be claimed.')
pack.add_file('audit/' + a.population + '/physical-caps.json', a.caps.read_bytes())
db.execute('INSERT OR REPLACE INTO reports VALUES(?,?)',
           ('failure-audit-' + a.population, json.dumps(summary)))
db.commit()
print(json.dumps({k:v for k,v in summary.items() if k not in ['stage_categories','causes']}))
