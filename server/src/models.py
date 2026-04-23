from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, Relationship, SQLModel, select

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

# Create a local mapping for fast lookups
CLASS_MAP = {
    "scout": 0, "soldier": 1, "pyro": 2, "demoman": 3,
    "heavyweapons": 4, "engineer": 5, "medic": 6, "sniper": 7, "spy": 8
}

def get_class_id_from_name(name: str) -> int:
    # logs.tf sometimes uses 'heavyweapons' instead of 'heavy'
    normalized_name = name.lower()
    return CLASS_MAP.get(normalized_name, 0) # Default to Scout if unknown

async def get_or_create_player(db: AsyncSession, steam_id: str, current_name: str) -> int:
    # 1. Search for the player by SteamID
    statement = select(Player).where(Player.steamid == steam_id)
    result = await db.execute(statement)
    player = result.scalars().first()
    
    if not player:
        # 2. If they don't exist, create them
        player = Player(steamid=steam_id, last_known_name=current_name)
        db.add(player)
        await db.flush()  # Generate ID within current transaction
        await db.refresh(player)
    else:
        # Update the name if it has changed
        player.last_known_name = current_name
        await db.flush()

    await db.refresh(player)
    return player.id #type: ignore

async def seed_classes(session: AsyncSession):
    # The 9 official TF2 classes
    tf2_classes = [
        "Scout", "Soldier", "Pyro", "Demoman", 
        "Heavy", "Engineer", "Medic", "Sniper", "Spy"
    ]

    for index, name in enumerate(tf2_classes):
        # Check if this class already exists
        statement = select(Class).where(Class.name == name)
        result = await session.execute(statement)
        existing_class = result.scalars().first()

        if not existing_class:
            # We use the list index as the ID to keep it consistent (0-8)
            new_class = Class(id=index, name=name)
            session.add(new_class)
    
    await session.commit()


async def get_or_create_tournament(db: AsyncSession, tournament_id: int, name: str | None = None):
    statement = select(Tournament).where(Tournament.id == tournament_id)
    result = await db.execute(statement)
    tournament = result.scalars().first()

    if not tournament:
        tournament = Tournament(
            id=tournament_id,
            name=name or f"Tournament {tournament_id}"
        )
        db.add(tournament)
        await db.flush()
        await db.refresh(tournament)

    return tournament