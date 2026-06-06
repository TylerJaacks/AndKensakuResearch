# And-Kensaku (安藤ケンサク) Research
Reverse engineering the Japanese exclusive Wii game [And-Kensaku (安藤ケンサク)](https://nintendo.fandom.com/wiki/And-Kensaku).


> And-Kensaku (安藤ケンサク) is a game where you can enjoy various word games by using "hits" that indicate how many words or phrases are used on the Internet.
> Play while thinking about how a word is used, what kind of word is popular, the topic of the world, and a combination of likely words.
> You may find an unexpected gap with your thinking. The game contains over > 10,000 words and phrases, so you can play without connecting to the Internet.
> In addition, if you connect to the Internet, you can download the latest words, hits, and additional questions from time to time, and enjoy information that reflects actual trends.

*Reference: [Dolphin Wiki](https://wiki.dolphin-emu.org/index.php?title=And-Kensaku)*


![image](https://static.wikitide.net/wuhupediawiki/b/b4/And-Kensaku.png)

# TR2 File Format
[Here](/docs/TR2.md)

# PATCHES

In order to make changes to the Puzzle.tr2 (The only supported file at this time) you need to disable signature checks for tr2 files.
There a set of patches, [RK3J01.gct](patches/RK3J01.gct) this is the Gecko code for a real Wii, and [RK3J01.ini](patches/RK3J01.ini) patches for Dolphin.

# CREDITS

Claude helped a lot during this process (Yeah, yeah shut up. I know how to code).
