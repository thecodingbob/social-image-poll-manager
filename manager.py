from configparser import ConfigParser, SectionProxy
from facebook import GraphAPI
from datetime import timedelta
from PIL import Image
from os import path


class Reaction:
    def __init__(self, name: str, image: Image, emoji: str):
        self.name = name
        self.image = image
        self.emoji = emoji


class PollManager:

    def __init__(self, graph_api: GraphAPI, album_id: str, winner_album_id: str,
                 reactions: list[Reaction], layout: tuple[int], max_posts_per_time: int,
                 voting_duration: timedelta, poll_name: str):
        self.graph_api = graph_api
        self.reactions = reactions
        self.layout = layout
        self.max_posts_per_time = max_posts_per_time
        self.voting_duration = voting_duration
        self.poll_name = poll_name
        self.album_id = album_id
        self.winner_album_id = winner_album_id


def init_reactions(config: SectionProxy):
    base_dir = config.get("base_dir")
    names = config.get("names").split(",")
    emojis = config.get("emojis").split(",")
    image_names = config.get("images").split(",")
    reactions = []
    for (idx, image_name) in enumerate(image_names):
        image = Image.open(path.join(base_dir, image_names[idx]))
        reactions.append(Reaction(names[idx], image, emojis[idx]))
    return reactions


def collect_images_from_albums(album_ids: list[str], graph_api: GraphAPI):
    pass

def main():
    config = ConfigParser(allow_no_value=True)
    config.read('config.ini', encoding='utf-8')

    reactions = init_reactions(config["reactions"])

    fb_settings = config["facebook"]
    bot_settings = config["bot_settings"]

    page_id = fb_settings.get("page_id")
    access_token = fb_settings.get("access_token")
    # If album_id is missing, posts to timeline (using page_id)
    album_id = fb_settings.get("album_id", fallback=page_id)
    winner_album_id = fb_settings.get("winner_album_id")
    graph_api = GraphAPI(access_token=access_token, timeout=3000)

    images_source = bot_settings.get("images_source")
    if images_source == "ALBUM":
        images



if __name__ == "__main__":
    main()
