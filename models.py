class Player:
    def __init__(self, name, position, price, total_points, form, team):
        self.name = name
        self.position = position
        self.price = price  
        self.total_points = total_points
        self.form = form
        self.team = team

    def points_per_million(self):
        """Calculates points per million for the player"""
        if self.price == 0:
            return 0
        return round(self.total_points/ self.price, 2)

    def is_premium(self, threshold=8.0):
        """Determines if the player is considered premium based on price"""
        return self.price >= threshold


    def __repr__(self):
        return f"<Player {self.name} ({self.position}) -- {self.total_points}pts>"