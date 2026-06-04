"""
make_test_misc.py - produce an obvious, visible Misc.tr2 edit for in-game testing.

Target word: 映画 (id 29).  Changes designed to be unmistakable in the
graph/trend quiz:
  - SINGLEHITS 9345 -> 1 (lowest possible; graph bar should be tiny / value tiny)
  - WORD_RANK S(0) -> E(5) (the lowest rank)
As a second, even more obvious tell, we also rename it visibly.
"""
from tr2 import Tr2

if __name__ == '__main__':
    t = Tr2('../tr2/Misc.tr2')
    ID = 29  # 映画

    # 1) crater its popularity so the graph/number is obviously wrong
    t.get('SINGLEHITS').set_value(ID, 1)

    # 2) drop its rank to E
    t.get('WORD_RANK').set_value(ID, 5)

    # 3) rename it so it's visually unmistakable on screen
    t.get('WordList').set_value(ID, '★テスト改造★')
    # keep a reading so the game can render/sort it
    t.get('YOMI').set_value(ID, 'てすとかいぞう')

    t.save('Misc_test.tr2')
    print('wrote Misc_test.tr2')

    # verify re-parse
    v = Tr2('Misc_test.tr2')
    print('WordList[29]  =', v.read('WordList')[ID])
    print('YOMI[29]      =', v.read('YOMI')[ID])
    print('SINGLEHITS[29]=', v.read('SINGLEHITS')[ID])
    print('WORD_RANK[29] =', v.read('WORD_RANK')[ID], '(0=S..5=E)')
