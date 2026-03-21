from awpy import Demo, Nav, Spawns

from pprint import pprint


class DemoScraper:
    def __init__(self, demo_path: str):
        self.demo_path = demo_path
        self.data = None

    def print_tables(self, demo: Demo):
        """Prints the tables of the demo for debugging purposes"""
        print("\n[DemoScraper] header:")
        pprint(demo.header)

        print("\n[DemoScraper] Rounds:")
        pprint(demo.rounds)

        print("\n[DemoScraper] Kills:")
        pprint(demo.kills)

        print("\n[DemoScraper] Grenades:")
        pprint(demo.grenades)

        print("\n[DemoScraper] Damages:")
        pprint(demo.damages)


    def parse(self, path: str = None):
        """Parse the demo file using awpy"""
        demo_path = path or self.demo_path
        demo = Demo(path=demo_path)
        print(f"[DemoScraper] Parsing demo: {demo_path}")
        demo.parse()
        print("[DemoScraper] Parsing complete.")
        self.print_tables(demo)

   



    def run(self, path: str = None):
        """Convenience method: parse + print"""
        self.parse(path)