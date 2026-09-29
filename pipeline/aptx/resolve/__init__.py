"""The actor registry: one actor per real-world group, merged across sources.

names.py turns names into matching keys, and registry.py merges source records
that share a key, keeps the evidence for each merge, refuses merges that would
join two ATT&CK groups, and types software names so they are not taken for
actors.
"""
