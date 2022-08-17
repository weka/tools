# Run to generate output like:
#
### Stripe: 4 + 2
### 1/96 buckets are down
### Working on node 1 (last node is 101)...Got placements from all nodes
### Active: 95 buckets
### Unresponsive: 1 buckets
### ------------------------------------
###   Must revive at least 1 of the following drives:
###     DiskId<1>
###     DiskId<2>

import subprocess
import json
import sys
from optparse import OptionParser

parser = OptionParser()
parser.add_option(
    "-v", "--verbose", action="store_true", default=False,
    help="make lots of noise [default]")
parser.add_option(
    "--batch", default=16, type="int",
    help="number of raid_placements manholes to concurrently execute")

def parse_typed_identifier(prefix):
    def parse(s):
        assert s.startswith(prefix + "<")
        assert s.endswith(">")
        content = s[len(prefix)+1:-1]
        if content == "INVALID":
            return None
        return int(content)
    return parse

parse_bucket_id = parse_typed_identifier("BucketId")
parse_disk_id = parse_typed_identifier("DiskId")
parse_node_id = parse_typed_identifier("NodeId")
parse_placement_idx = parse_typed_identifier("PlacementIdx")

def json_call(*args, **kw):
    return json.loads(subprocess.check_output(*args, **kw))

def get_status():
    return json_call(["weka", "status", "-J"])

def get_rebuild_status():
    return json_call(["weka", "status", "rebuild", "-J"])

def chunks(seq, size):
    return (seq[i:i+size] for i in range(0, len(seq), size))

class JsonCall:
    def __init__(self, *args, **kw):
        self.cmd = args
        self.popen = subprocess.Popen(*args, stdout=subprocess.PIPE, **kw)
    def result(self):
        assert self.popen.stdout
        output = self.popen.stdout.read()
        code = self.popen.wait()
        if code != 0:
            print(self.cmd, ":", code)
            raise subprocess.CalledProcessError(returncode=code, cmd=self.cmd)
        return json.loads(output)

def raid_placements(node_id):
    return JsonCall(["weka", "debug", "manhole", "--node=%s" % node_id, "raid_placements"])

def get_enabled_bits(num):
    idx = 0
    while num != 0:
        if num & 1: yield idx
        num //= 2
        idx += 1

def space_separated(seq):
    return " ".join(str(x) for x in seq)

def main(*, verbose, batch_size):

    def verbose_print(*args, **kw):
        if verbose:
            print(*args, **kw)

    status = get_status()
    buckets = status["buckets"]

    D = status["stripe_data_drives"]
    P = status["stripe_protection_drives"]
    print("Stripe: %s + %s" % (D, P))

    active_buckets = buckets['active']
    total_buckets = buckets['total']

    if active_buckets == total_buckets:
        print("All %s buckets up!" % (total_buckets,))
        rs = get_rebuild_status()
        # from pprint import pprint
        # pprint(rs)
        if rs["unavailablePercent"] == 0:
            print("AND all data is available")
    else:
        print("%s/%s buckets are down" % (total_buckets - active_buckets, total_buckets))

    buckets_by_state = {}
    for bucket_json in json_call(["weka", "cluster", "buckets", "-J"]):
        bucket_id = parse_bucket_id(bucket_json['bucket_id'])
        init_state = bucket_json["init_state"]
        buckets_by_state.setdefault(init_state, set()).add(bucket_id)

    compute_node_ids = [
        parse_node_id(node_dict["node_id"])
        for node_dict in json_call(["weka", "cluster", "nodes", "-b", "-J"])
        if "COMPUTE" in node_dict["roles"]
    ]

    placements = {}
    buckets_of_node = {}
    for nodes in chunks(compute_node_ids, batch_size):
        print("\rWorking on node %s (last node is %s)..." % (nodes[0], compute_node_ids[-1]), end='')
        calls = [(node_id, raid_placements(node_id)) for node_id in nodes]
        for node_id, call in calls:
            for plcDesc, info in call.result().items():
                desc = json.loads(plcDesc)
                bucket_id = parse_bucket_id(desc["bucketId"])
                placement_idx = parse_placement_idx(desc["placementIdx"])
                bucketDict = placements.setdefault(bucket_id, {})
                buckets_of_node.setdefault(node_id, set()).add(bucket_id)
                if placement_idx in bucketDict:
                    print("WARNING: duplicate %s\n" % (desc,))
                bucketDict[placement_idx] = dict(disks=[parse_disk_id(disk_id_str) for disk_id_str in info["disks"]["_array"]], dirty=info["dirtyDisks"], down=info["downDisks"])
    print("Got placements from all nodes")
    verbose_print("")
    verbose_print("Got bucket reports in nodes:")
    for node_id, bucket_ids in buckets_of_node.items():
        verbose_print(("NodeId<%s>:" % node_id).ljust(16), space_separated(bucket_ids))

    needed_recoveries = []
    for init_state, buckets in buckets_by_state.items():
        verbose_print("-------------------------------")
        print("%s: %s buckets" % (init_state, len(buckets)))
        buckets_of_failures = {}
        for bucket_id in buckets:
            if bucket_id not in placements:
                print("ERROR: Could not get placements report for %s from any COMPUTE node" % (bucket_id,))
                continue
            for placement_idx, info in placements[bucket_id].items():
                disks = info["disks"]
                if all(disk_id is None for disk_id in disks):
                    print("WARNING: BucketId<%s>:PlacementIdx<0x%x> could not probe its disks" % (bucket_id, placement_idx))
                    continue

                dirty_disks = frozenset(disks[i] for i in get_enabled_bits(info['dirty']))
                down_disks  = frozenset(disks[i] for i in get_enabled_bits(info['down']))
                buckets_of_failures.setdefault((dirty_disks, down_disks), set()).add(bucket_id)
        verbose_print()
        for (dirty_disks, down_disks), bucket_ids in buckets_of_failures.items():
            if not dirty_disks and not down_disks: continue

            failure_count = len(dirty_disks | down_disks)

            verbose_print("------------------------------------------")
            verbose_print("The following %sfailure pattern:" % ("too many " if failure_count > P else "",))
            verbose_print("  DIRTY: ", list(dirty_disks))
            verbose_print("  DOWN:  ", list(down_disks))

            if failure_count > P:
                verbose_print("exists in %s buckets: %s" % (len(bucket_ids), space_separated(bucket_ids)))
                need_revival = failure_count - P
                revivable = down_disks - dirty_disks
                verbose_print()
                assert len(revivable) >= need_revival
                needed_recoveries.append((need_revival, revivable))
            else:
                verbose_print("exists in %s buckets" % (len(bucket_ids),))
        verbose_print()

    print_needed_recovery(needed_recoveries)

def print_needed_recovery(needed_recoveries):
    print("------------------------------------")
    must_revive = set()
    for need_revival, revivable in needed_recoveries:
        if need_revival == len(revivable):
            must_revive |= revivable

    if must_revive:
        print("To recover buckets, must revive drives:")
        for disk_id in must_revive:
            print("  DiskId<%s>" % (disk_id,))

    new_needed_recoveries = []
    for need_revival, revivable in needed_recoveries:
        need_revival -= len(revivable & must_revive)
        revivable = revivable - must_revive
        if need_revival > 0:
            new_needed_recoveries.append((need_revival, revivable))

    # sort by size of revivable set
    new_needed_recoveries.sort(key = lambda pair: len(pair[1]))

    for i, (need_revival, revivable) in enumerate(new_needed_recoveries):
        for smaller_need_revival, smaller_revivable in new_needed_recoveries[:i]:
            if smaller_revivable <= revivable and smaller_need_revival >= need_revival:
                # This case is weaker than the previously handled case
                break
        else:
            print("  Must revive at least %s of the following drives:" % (need_revival,))
            for disk_id in revivable:
                print("    DiskId<%s>" % (disk_id,))

if __name__ == '__main__':
    options, args = parser.parse_args()
    if args:
        parser.error('Invalid arguments: %s' % args)
        sys.exit(2)
    assert options.batch >= 1
    assert options.batch <= 2048
    main(verbose=options.verbose, batch_size=options.batch)
