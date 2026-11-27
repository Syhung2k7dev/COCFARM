# Templates

The bot recognises buttons by matching small PNG crops, and reads numbers
with digit shapes learned from screenshots. All of them are taken from
screens scaled to **920 px tall**; `farmbot screenshot` saves screens at that
size, so crop coordinates from its output can be used directly.

## What's included

Every picture the bot uses ships in this folder (`farmbot pictures` lists them
and flags any that are missing):

| Folder | What |
|---|---|
| `buttons/` | Home village and battle buttons: Battle, Find a Match, Attack!, Next, End Battle, Okay, Return Home, Magic Items inventory, rewards, event chests, walls, clan chat, requests, donations, disconnect popups |
| `builder/` | Builder base: the boats, Builder Battle, Find Now!, battle start/end, hero cards, speed, collector bubbles, the elixir cart, walls |
| `collectors/` | Full gold mine, elixir collector and dark elixir drill bubbles |
| `donate/` | Each donatable unit as it looks in the donate window (`donate/<name>.png`, the name as in `farmbot/units.py`; `name@2.png` is a second look of the same unit) |
| `fonts/loot/` | Digit shapes for reading loot numbers |

A picture that is a folder (for example `buttons/battle/`, `buttons/okay/`)
holds several variants of one button; any of them counts as a match.

## Making one

The easiest way is the GUI's **Pictures** page: pick the picture, press
**Take screenshot** while its screen is showing (or open a saved screenshot),
drag a box around the button's text, and press **Save picture**.

From the command line (`farmbot pictures` lists what is missing):

```sh
farmbot screenshot screens/result.png
# open it in an image editor, note x, y, width, height of the button
farmbot crop screens/result.png 880 760 240 70 buttons/return_home
farmbot locate buttons/return_home --image screens/result.png   # aim for a score above 0.9
```

Crop tightly around the button's text. Leave out timers, costs and anything animated.

## Re-learning digits

If loot numbers read wrong (for example after a game update changes the font),
learn them again from a scouting screenshot. Give the region around one number
and the number shown:

```sh
farmbot learn-digits screens/scout.png 195 92 150 34 "1 582 869" --replace
farmbot inspect --image screens/scout.png
```


## Magic Items inventory

The October 2026 village interface has a dedicated Magic Items button shared with
Magic Snacks, beside the Build controls. To let COCFARM open the inventory, add
both templates from the GUI's **Pictures** page:

- `buttons/magic_items`: crop the dedicated Magic Items / Magic Snacks button
  on the village screen.
- `buttons/magic_items_title`: crop the **Magic Items** heading inside the
  opened inventory.

Capture each from your own emulator at the normal 920 px screenshot height.
The navigation routine refuses to tap if either template is missing, and it
checks that the Magic Items heading appears after the tap. It does not select
or consume an item.

## Asset capture checklist

Some strategy branches and newer inventory features need account-specific or game-version-specific templates that are not shipped as generic defaults. Capture them from your own emulator through **Pictures** at the documented 920 px screenshot height. In particular, the Magic Items inventory requires both `buttons/magic_items` and `buttons/magic_items_title`; optional attack recognition may also use `cards/healer`, `cards/ground`, `cards/lure`, `buildings/clan_castle` and `buildings/loot`. Do not substitute generated or unrelated images: a template must match the real in-game crop. The personal `redact/castle_badge` remains local and is not committed.
