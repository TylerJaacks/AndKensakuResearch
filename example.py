"""
edit_example.py - how to create a modified .tr2 word list for sideloading.

Run:  python3 edit_example.py (expects Misc.tr2 in the same folder)
Produces Misc_modified.tr2.
"""

"""
Misc.tr2 — the master single-word database plus shared engine config. 
This is the central file. It holds the WordList (the search terms) 
with parallel YOMI (readings), SINGLEHITS (popularity score per word), 
and WORD_RANK (S–E), all joined by id. Plus the genre system 
(MainGenreList, SubGenreList, SUB_GENRE_A–D, GenreTable), 
the Serial (dataset version), COUPLEWORDS (and-search pair hits), 
and per-minigame parameter tables (KAKUNOU_*, STEP_WORDS, SHOOTING_*, QUEST_MAXHP). 
If you change which single words exist and how popular they are, this is the file.

Phrase.tr2 — phrase content and the comparison-mode data. Richest file (133 sections). 
It has PHRASENAME/PHRASEYOMI/PHRASEHITS (multi-word phrases with readings and popularity), 
and the entire 502 どっち ("which is more popular?") mode: 
question sets, the two choices per question (502_DOTCH_SELECT1/2) 
with their individual hit counts (502_DOTCH_HIT1/2), comments, and robot dialogue. 
It also carries the 503 ブログ (blog-trend) mode and calendar/developer-list data. 
This is the head-to-head "guess the winner" content.
Puzzle.tr2 — the puzzle/word-game vocabularies. 
I'd earlier called this "crossword," but parsing 
it corrected that: it's actually got 1618 sections 
covering multiple word games, with 109_SHIRITORI_* 
(the しりとり / word-chain mode) prominently — stage tefuda (hands), 
fields, themes, hits, norma (targets) per stage. So it's the per-stage 
vocabulary and parameters for the puzzle-style modes, not just crosswords.

Double00.tr2, Double01.tr2, Double02.tr2 — the co-occurrence data, 
internally DoubleRecord_00/01/02, 2.25 MB each. These are the pairwise 
"A and B together" hit tables — the dense data behind COUPLEWORDS a
nd the and-search scoring. They're split into three files 
and use the cell-array structure (tr2GetU32CellArrayByIDAH 
from the symbol table confirms one key → many paired values). 
This is what lets the game answer "how many results for term A and term B."
"""

from tr2 import Tr2

t = Tr2('tr2\\Misc.tr2')

# 1) Change a word's popularity score (scalar; safe, same-length edit).
#    SINGLEHITS is keyed by the same id as WordList.
hits = t.get('SINGLEHITS')
hits.set_value(12, 9999)  # id 12 == "アカデミー"; bump its hit score

# 2) Replace a term's text (variable length; encoder recomputes offsets).
words = t.get('WordList')
words.set_value(12, 'スーパーアカデミー')

# 3) Change a rank (S=0,A=1,B=2,C=3,D=4,E=5).
rank = t.get('WORD_RANK')
rank.set_value(12, 0)  # force rank S

# 4) Add a brand-new word with id 9000 (must add matching entries in the
#    parallel sections so the game has reading/hits/rank for it).
words.set_value(9000, 'ニューワード')
t.get('YOMI').set_value(9000, 'にゅーわーど')
hits.set_value(9000, 8800)
rank.set_value(9000, 1)

t.save('Misc_modified.tr2')
print('wrote Misc_modified.tr2')

# verify it reparses
v = Tr2('Misc_modified.tr2')
print('readback WordList[12] =', v.read('WordList')[12])
print('readback SINGLEHITS[12] =', v.read('SINGLEHITS')[12])
print('readback WordList[9000] =', v.read('WordList').get(9000))