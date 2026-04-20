from typing import List, Optional
from sqlmodel import Field, Relationship, SQLModel, Session, select

class Tournament(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    matches: List["Match"] = Relationship(back_populates="tournament")

class Player(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    steamid: str = Field(unique=True, index=True)
    last_known_name: Optional[str] = None # Add this field

class Match(SQLModel, table=True):
    __tablename__ = "matches" # type: ignore
    id: Optional[int] = Field(default=None, primary_key=True)
    log_id: int = Field(index=True, unique=True)
    map: str
    tournament_id: int = Field(foreign_key="tournament.id", index=True)
    
    tournament: Tournament = Relationship(back_populates="matches")
    stats: List["MatchStat"] = Relationship(back_populates="match")

class MatchStat(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    match_id: int = Field(foreign_key="matches.id", index=True)
    player_id: int = Field(foreign_key="player.id", index=True)
    class_id: int = Field(foreign_key="classes.id", index=True)
    team: str
    playtime: int
    kills: int
    deaths: int
    dpm: float
    primary_accuracy: float
    damage_dealt: int
    damage_received: int
    heals_received: int
    headshots: Optional[int]
    backstabs: Optional[int]
    airshots: Optional[int]
    captures: int
    
    match: Match = Relationship(back_populates="stats")
    medic_detail: Optional["MedicStat"] = Relationship(back_populates="parent_stat")
    player_class: "Class" = Relationship(back_populates="stats")

class MedicStat(SQLModel, table=True):
    # The primary key is also the foreign key (1:1 relationship)
    matchstat_id: int = Field(foreign_key="matchstat.id", primary_key=True)
    player_id: int = Field(foreign_key="player.id", index=True)
    ubers: int
    drops: int
    healing_done: int
    hpm: float
    
    parent_stat: MatchStat = Relationship(back_populates="medic_detail")

class Class(SQLModel, table=True):
    __tablename__ = "classes" # type: ignore
    id: int = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)

    # Relationship back to stats (optional but helpful)
    stats: List["MatchStat"] = Relationship(back_populates="player_class")


def save_complete_match(db: Session, logs_json: dict, tournament_id: int):
    # 1. Create the Match object
    new_match = Match(
        log_id=logs_json["info"]["id"],
        map=logs_json["info"]["map"],
        tournament_id=tournament_id
    )
    db.add(new_match)
    db.flush()

    # 2. Iterate through players in the JSON
    for steam_id, p_data in logs_json["players"].items():
        # Loop through classes they played
        for c_stats in p_data.get("class_stats", []):
            total_time = c_stats.get("total_time", 0)
            dpm = c_stats.get("dmg", 0) / (total_time / 60) if total_time > 0 else 0
            player_id = get_or_create_player(db, steam_id, logs_json["names"][steam_id])
            
            # Create the MatchStat entry
            stat_entry = MatchStat(
                match_id=new_match.id, # type: ignore[arg-type]
                player_id=player_id,
                class_id=get_class_id_from_name(c_stats["type"]),
                team=p_data.get("team", "Unknown"),
                playtime=total_time,
                kills=c_stats["kills"],
                deaths=c_stats["deaths"],
                dpm=dpm,
                primary_accuracy=c_stats.get("weapon", {}).get("primary", {}).get("acc", 0.0),
                damage_dealt=c_stats.get("dmg", 0),
                damage_received=p_data.get("dt", 0),
                heals_received=p_data.get("hr", 0),
                headshots=c_stats.get("headshots", 0),
                backstabs=c_stats.get("backstabs", 0),
                airshots=c_stats.get("as", 0),
                captures=c_stats.get("cpc", 0)
            ) # type: ignore

            # 3. If they are a Medic, attach MedicStat directly to stat_entry
            if c_stats["type"].lower() == "medic":
                healing_done = p_data.get("heal", 0)
                hpm = healing_done / (total_time / 60) if total_time > 0 else 0
                stat_entry.medic_detail = MedicStat(
                    player_id=player_id,
                    ubers=p_data.get("ubers", 0),
                    drops=p_data.get("drops", 0),
                    healing_done=healing_done,
                    hpm=hpm
                ) # type: ignore

            # Add this stat entry to the match's list
            new_match.stats.append(stat_entry)
            db.add(stat_entry)
            db.flush()

    # 4. Save everything in ONE transaction
    db.commit() 
    db.refresh(new_match)
    return new_match

# Create a local mapping for fast lookups
CLASS_MAP = {
    "scout": 0, "soldier": 1, "pyro": 2, "demoman": 3,
    "heavyweapons": 4, "engineer": 5, "medic": 6, "sniper": 7, "spy": 8
}

def get_class_id_from_name(name: str) -> int:
    # logs.tf sometimes uses 'heavyweapons' instead of 'heavy'
    normalized_name = name.lower()
    return CLASS_MAP.get(normalized_name, 0) # Default to Scout if unknown

def get_or_create_player(db: Session, steam_id: str, current_name: str) -> int:
    # 1. Search for the player by SteamID
    statement = select(Player).where(Player.steamid == steam_id)
    player = db.exec(statement).first()
    
    if not player:
        # 2. If they don't exist, create them
        player = Player(steamid=steam_id, last_known_name=current_name)
        db.add(player)
        db.flush()  # Generate ID within current transaction
        db.refresh(player)
    else:
        # Update the name if it has changed
        player.last_known_name = current_name
        db.flush()

    db.refresh(player)
    return player.id #type: ignore

def seed_classes(session: Session):
    # The 9 official TF2 classes
    tf2_classes = [
        "Scout", "Soldier", "Pyro", "Demoman", 
        "Heavy", "Engineer", "Medic", "Sniper", "Spy"
    ]

    for index, name in enumerate(tf2_classes):
        # Check if this class already exists
        statement = select(Class).where(Class.name == name)
        existing_class = session.exec(statement).first()

        if not existing_class:
            # We use the list index as the ID to keep it consistent (0-8)
            new_class = Class(id=index, name=name)
            session.add(new_class)
    
    session.commit()


def get_or_create_tournament(db: Session, tournament_id: int, name: str | None = None):
    statement = select(Tournament).where(Tournament.id == tournament_id)
    tournament = db.exec(statement).first()

    if not tournament:
        tournament = Tournament(
            id=tournament_id,
            name=name or f"Tournament {tournament_id}"
        )
        db.add(tournament)
        db.flush()
        db.refresh(tournament)

    return tournament