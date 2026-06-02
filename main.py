from tr2 import Tr2

if __name__ == '__main__':
    double00_tr2 = Tr2('tr2\\Double00.tr2')
    double01_tr2 = Tr2('tr2\\Double01.tr2')
    double02_tr2 = Tr2('tr2\\Double02.tr2')
    misc_tr2 = Tr2('tr2\\Misc.tr2')
    phrase_tr2 = Tr2('tr2\\Phrase.tr2')
    puzzle_tr2 = Tr2('tr2\\Puzzle.tr2')

    print(double00_tr2.summary())
    print(double01_tr2.summary())
    print(double02_tr2.summary())
    print(misc_tr2.summary())
    print(phrase_tr2.summary())
    print(puzzle_tr2.summary())
