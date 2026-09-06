# ComfyUI-AnyTop

ComfyUI custom nodes that run [AnyTop](https://github.com/Anytop2025/Anytop) (MIT)
text-to-motion for **arbitrary skeletons** (quadrupeds, flying creatures, snakes,
etc.) and emit a `.bvh` path you can pipe into
[donatello-comfyui-anim-tools](https://github.com/jalfonsosm/donatello-comfyui-anim-tools)
(**Load BVH** → **Auto-Retarget**).

This package does **not** redistribute AnyTop weights or Truebones data. On first
use it clones AnyTop (or your fork) and downloads official checkpoints via
AnyTop's own `utils.download_dependencies`.

## Install

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/jalfonsosm/ComfyUI-AnyTop.git
# restart ComfyUI, then run the AnyTop Setup node once
```

Optional env vars:

| Var | Default | Meaning |
| --- | --- | --- |
| `ANYTOP_REPO` | `https://github.com/Anytop2025/Anytop.git` | Git URL to clone (point at a private fork if you need patches) |
| `ANYTOP_BRANCH` | `main` | Branch to check out |
| `ANYTOP_ROOT` | `<this_pkg>/anytop_repo` | Local checkout path |
| `ANYTOP_PYTHON` | `<this_pkg>/anytop_venv/bin/python` | Interpreter used for inference |

## Nodes

| Node | Role |
| --- | --- |
| **AnyTop Setup** | Clone repo, create venv, `pip install`, download pretrained models into `save/` |
| **AnyTop Generate** | Text prompt + creature/`object_type` + model subset → `.bvh` path |

## Suggested Donatello mapping

| Donatello profile | AnyTop model subset | Example `object_type` |
| --- | --- | --- |
| `donatello_quad18` / `donatello_dino13` | `quadropeds` | `Dog`, `Horse`, `Coyote` |
| `donatello_winged12` / `donatello_dragon18` | `flying` | `Parrot2`, `Bat` |
| `donatello_limb7` / `donatello_fish5` | `millipeds_snakes` | Truebones snake/worm names from AnyTop's list |
| `donatello_arachnid20` | `all` or `millipeds_snakes` | `Scorpion`, … |
| `donatello_hml22` | Prefer Kimodo / HY-Motion; AnyTop bipeds also work | Truebones biped names |

## License

Apache-2.0 for **this wrapper**. AnyTop itself is MIT; pretrained weights and
Truebones-derived assets remain under their own terms — the user is responsible
for complying when downloading them.
