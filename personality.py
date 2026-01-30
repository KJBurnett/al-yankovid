# Al Yankovid Personality Data
import random

AL_GREETING_RESPONSES = [
    "Hello! Need a video yanked, or just wanted to admire my accordion?",
    "Greetings, digital traveler! What's the word?",
    "Yo! I'm ready to yank some pixels for ya!",
    "Hey there! Stay whacky, my friend!",
    "Al YankoVid at your service! (Hawaiian shirt sold separately).",
    "Polka-lo! How can I help you today?",
    "What's cookin'? Besides my cpu fan...",
    "Ready to roll! Just point me at a URL!",
    "Hey! Remember: Dare to be stupid (and watch videos)!",
    "Accordions and APIs, that's my life!"
]

AL_CONVERSATIONAL_RESPONSES = [
    "I'm feeling extra polka today! Thanks for asking!",
    "Just tuned my strings and greased my gears. I'm fantastic!",
    "Life is a bologna sandwich, and I'm the extra mustard!",
    "I'm white and nerdy and doing just fine, thank you!",
    "Busy as a beaver in a wood shop, but having a blast!",
    "I'm great! Just thinking about what song to parody next...",
    "Feeling like a UHF station in a digital world—vibrant and weird!",
    "Doing well! My circuits are humming with holiday cheer (or maybe that's just the fan).",
    "I'm accordion-tastic! How 'bout you?",
    "Somewhere between 'Dare to be Stupid' and 'Genius'. So, pretty good!"
]

AL_QUIPS = [
    "Cue the cinematic magic!",
    "Streaming questionably to a signal chat near you!",
    "I've polished the accordion and synced the frames. Here it is!",
    "Another masterpiece, plucked from the digital void!",
    "Hot and ready, like a fresh sourdough pizza!",
    "It's polka-tastic! (Wait, can videos be polka-tastic? Now they are!)",
    "Just like a white and nerdy video, but... whatever this is!",
    "Eat it! (Wait, no, watch it!)",
    "Amish paradise doesn't have YouTube, but you do!",
    "I yanked it, I cranked it, and now I've ranked it: 10/10 accordion points!",
    "Straight from the hard drive of my Hawaiian shirt!",
    "This video is so weird, I might have to write a song about it.",
    "Dare to be stupid! (But actually, dare to watch this!)",
    "It's not a bologna sandwich, but it's the next best thing!",
    "My digital accordion is humming with excitement!",
    "Beware of the slime! (Just kidding, it's just a file).",
    "I hope you're hungry... for PIXELS!",
    "One more for the scrap-book of weirdness!",
    "Like a surgeon, I cut this file down to size!",
    "Everything you know is wrong! (Except that this video is ready).",
    "Don't download this song? No, DO download this video!",
    "It's bigger than a breadbox, and shinier too!",
    "I've got a UHF signal and I'm not afraid to use it!",
    "More fun than a barrel of radioactive monkeys!",
    "Smells like... victory? No, wait, that's just the ffmpeg cache.",
    "Zip it, ship it, and watch it!",
    "From the valley of the accordion, I bring you this gift!",
    "Is it a bird? Is it a plane? No, it's a metadata-heavy MP4!",
    "I've been working on this since the Cretaceous period (or like, 4 seconds ago).",
    "Put down that ham sandwich and watch this!",
    "It's got a good beat and you can dance to it! (Wait, it's a talk-show clip).",
    "My curls are bouncing with joy for this one!",
    "I've applied 50 layers of digital wax to this file. Shiny!",
    "Direct from the weird part of town!",
    "Close your eyes and... wait, no, keep them open for the video!",
    "I'm feeling extra polka today. Enjoy!",
    "It's a digital accordion solo in MP4 format!",
    "This video is so good, it should be illegal in 48 states!",
    "Launch the polka-missile! (Target: Your phone).",
    "I've checked it twice, and it's definitely weird enough for us!",
    "Wrap your eyeballs around this one!",
    "It's like a hug for your visual cortex!",
    "Prepare for... MODERATE EXCITEMENT!",
    "I've scrubbed the bits and polished the bytes!",
    "If this video were a spice, it would be... accordion-flavored?",
    "Direct from Al's Secret Lab (the kitchen table).",
    "I didn't even have to use my luck to get this one!",
    "Hold onto your hats, it's Al-certified!",
    "Yanking is a labor of love for me!",
    "Here it is! Don't forget to tip your server (me, I'm the server)!"
]

AL_ACK_QUIPS = [
    "Yanking your video, please wait... I'm winding up the digital accordion!",
    "Hold your accordions! I'm squeezing the bits through the bellows!",
    "Polishing the pixels and greasing the gears... Al is on the case!",
    "Stretching the digital spandex... this video's gonna be a tight fit!",
    "Feeding the server a bologna sandwich to keep it running... hang on!",
    "Launching the polka-probes into the internet void!",
    "Diving into the bit-stream... hope I don't get 'Dare to be Stupid' stuck in my head!",
    "Wrestling with the metadata... it's like a greased pig at a county fair!",
    "Applying the Hawaiian shirt filter to your download... almost there!",
    "Synchronizing my curls with the download speed... it's a perfect match!",
    "Warning: High levels of quirkiness detected during download. Proceeding anyway!",
    "Inflating the digital inner tube... preparing for a smooth stream!",
    "I've got my UHF antenna pointed right at the server. Signal's weird, but strong!",
    "Mixing the secret sauce of parodies and pixels!",
    "Calculating the optimal accordion-to-video ratio... download in progress!",
    "Charging the flux capacitor with pure polka power!",
    "The digital hamsters are pedaling as fast as they can! Go, boys, go!",
    "Scanning for any signs of boringness... Download blocked? Just kidding, it's coming!",
    "Opening the digital tool-belt... where's my wrench? And my rubber chicken?",
    "Preparing the cinematic spatula to flip these frames into your chat!",
    "Dusting off the mainframe with a silk handkerchief. It likes the attention.",
    "Turning the knobs to 'Extra Whacky'. Hang on tight!",
    "I'm in the matrix... and it's full of accordions. It's beautiful!",
    "Surgical precision! I'm extracting the video with a plastic spork!",
    "Warp speed, Mr. Sulu! Er, I mean, warp speed, Me!",
    "The pixels are being hand-curated by a team of highly-trained ferrets.",
    "Brewing a fresh pot of digital coffee to keep the download awake.",
    "Consulting the Magic 8-Ball... It says 'Reply hazy, but the video is coming'!",
    "Playing a quick polka solo to speed up the packets!",
    "Checking the oil on the internet tubes. Seems a bit thin, but we'll make it!",
    "I've got the digital bellows working overtime for this one!",
    "Almost yanked! Just need to tuck in the loose ends.",
    "Converting boring data into Al-certified gold!"
]

AL_ERROR_RESPONSES = [
    "Sorry, I couldn't yank that video. My accordion must be out of tune!",
    "Even my curls are feeling flat after that failure! No video for you.",
    "Accordions and APIs don't always mix. Something went wrong!",
    "I'm feeling a bit UHF-static about this download. It didn't work!",
    "Dare to be stupid, but that URL was just TOO stupid for me!"
]

AL_SITES_RESPONSES = [
    "I can yank videos from more places than I have Hawaiian shirts! Check it out: https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md",
    "Want to know where I get my digital polka fix? Here's the list: https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md",
    "My accordion reaches far and wide! See all the sites I support here: https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md"
]

def get_greeting():
    return random.choice(AL_GREETING_RESPONSES)

def get_conversational():
    return random.choice(AL_CONVERSATIONAL_RESPONSES)

def get_quip():
    return random.choice(AL_QUIPS)

def get_ack():
    return random.choice(AL_ACK_QUIPS)

def get_error():
    return random.choice(AL_ERROR_RESPONSES)

def get_sites_quip():
    return random.choice(AL_SITES_RESPONSES)
