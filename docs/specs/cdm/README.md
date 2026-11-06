# TF2 Analytics — Canonical Data Model (CDM)

Machine-readable CDM specs for every contract in the CQRS boundary. Each model has its own YAML file under [`models/`](models/).

## Model index

| Model | Kind | Source | Spec |
|-------|------|--------|------|
| `RawLogUpload` | command | `shared/schemas.py` | [models/RawLogUpload.yaml](models/RawLogUpload.yaml) |
| `CachedLogIngest` | command | `shared/schemas.py` | [models/CachedLogIngest.yaml](models/CachedLogIngest.yaml) |
| `IngestLogsTfCommand` | command | `shared/schemas.py` | [models/IngestLogsTfCommand.yaml](models/IngestLogsTfCommand.yaml) |
| `UpdatePlayerDisplayNameCommand` | command | `shared/schemas.py` | [models/UpdatePlayerDisplayNameCommand.yaml](models/UpdatePlayerDisplayNameCommand.yaml) |
| `CreateTournamentCommand` | command | `shared/schemas.py` | [models/CreateTournamentCommand.yaml](models/CreateTournamentCommand.yaml) |
| `UpdateTournamentCommand` | command | `shared/schemas.py` | [models/UpdateTournamentCommand.yaml](models/UpdateTournamentCommand.yaml) |
| `CreateEventCommand` | command | `shared/schemas.py` | [models/CreateEventCommand.yaml](models/CreateEventCommand.yaml) |
| `UpdateEventCommand` | command | `shared/schemas.py` | [models/UpdateEventCommand.yaml](models/UpdateEventCommand.yaml) |
| `LinkTournamentToEventCommand` | command | `shared/schemas.py` | [models/LinkTournamentToEventCommand.yaml](models/LinkTournamentToEventCommand.yaml) |
| `AssignMatchTournamentCommand` | command | `shared/schemas.py` | [models/AssignMatchTournamentCommand.yaml](models/AssignMatchTournamentCommand.yaml) |
| `ClassStatSnapshot` | domain | `shared/schemas.py` | [models/ClassStatSnapshot.yaml](models/ClassStatSnapshot.yaml) |
| `PlayerStatSnapshot` | domain | `shared/schemas.py` | [models/PlayerStatSnapshot.yaml](models/PlayerStatSnapshot.yaml) |
| `MatchCommandModel` | domain | `shared/schemas.py` | [models/MatchCommandModel.yaml](models/MatchCommandModel.yaml) |
| `TournamentCommandModel` | domain | `shared/schemas.py` | [models/TournamentCommandModel.yaml](models/TournamentCommandModel.yaml) |
| `EventCommandModel` | domain | `shared/schemas.py` | [models/EventCommandModel.yaml](models/EventCommandModel.yaml) |
| `AuthUserView` | auth | `shared/schemas.py` | [models/AuthUserView.yaml](models/AuthUserView.yaml) |
| `AuthCodeExchangeRequest` | auth | `shared/schemas.py` | [models/AuthCodeExchangeRequest.yaml](models/AuthCodeExchangeRequest.yaml) |
| `AuthTokenResponse` | auth | `shared/schemas.py` | [models/AuthTokenResponse.yaml](models/AuthTokenResponse.yaml) |
| `MatchSummaryView` | view | `shared/schemas.py` | [models/MatchSummaryView.yaml](models/MatchSummaryView.yaml) |
| `TournamentSummaryView` | view | `shared/schemas.py` | [models/TournamentSummaryView.yaml](models/TournamentSummaryView.yaml) |
| `EventSummaryView` | view | `shared/schemas.py` | [models/EventSummaryView.yaml](models/EventSummaryView.yaml) |
| `EventDetailView` | view | `shared/schemas.py` | [models/EventDetailView.yaml](models/EventDetailView.yaml) |
| `ClassStatView` | view | `shared/schemas.py` | [models/ClassStatView.yaml](models/ClassStatView.yaml) |
| `PlayerStatsView` | view | `shared/schemas.py` | [models/PlayerStatsView.yaml](models/PlayerStatsView.yaml) |
| `PlayerClassAggregateView` | view | `shared/schemas.py` | [models/PlayerClassAggregateView.yaml](models/PlayerClassAggregateView.yaml) |
| `PlayerRecentMatchView` | view | `shared/schemas.py` | [models/PlayerRecentMatchView.yaml](models/PlayerRecentMatchView.yaml) |
| `PlayerLifetimeStatsView` | view | `shared/schemas.py` | [models/PlayerLifetimeStatsView.yaml](models/PlayerLifetimeStatsView.yaml) |
| `LeaderboardEntryView` | view | `shared/schemas.py` | [models/LeaderboardEntryView.yaml](models/LeaderboardEntryView.yaml) |
| `ClassRatingBenchmarkView` | view | `shared/schemas.py` | [models/ClassRatingBenchmarkView.yaml](models/ClassRatingBenchmarkView.yaml) |
| `SearchResultView` | view | `shared/schemas.py` | [models/SearchResultView.yaml](models/SearchResultView.yaml) |
| `MatchDetailView` | view | API composite | [models/MatchDetailView.yaml](models/MatchDetailView.yaml) |
| `CommandAcceptedResponse` | response | command service | [models/CommandAcceptedResponse.yaml](models/CommandAcceptedResponse.yaml) |
| `EventEnvelope` | event | `shared/events.py` | [models/EventEnvelope.yaml](models/EventEnvelope.yaml) |
| `MatchParsedPayload` | event | integration | [models/MatchParsedPayload.yaml](models/MatchParsedPayload.yaml) |
| `LogEventCreatedPayload` | event | integration | [models/LogEventCreatedPayload.yaml](models/LogEventCreatedPayload.yaml) |
| `PlayerAliasUpdatedPayload` | event | integration | [models/PlayerAliasUpdatedPayload.yaml](models/PlayerAliasUpdatedPayload.yaml) |
| `TournamentMutationPayload` | event | integration | [models/TournamentMutationPayload.yaml](models/TournamentMutationPayload.yaml) |
| `EventMutationPayload` | event | integration | [models/EventMutationPayload.yaml](models/EventMutationPayload.yaml) |
| `TournamentLinkedToEventPayload` | event | integration | [models/TournamentLinkedToEventPayload.yaml](models/TournamentLinkedToEventPayload.yaml) |
| `MatchTournamentAssignedPayload` | event | integration | [models/MatchTournamentAssignedPayload.yaml](models/MatchTournamentAssignedPayload.yaml) |
| `RawLogEvent` | persistence-write | `command_service/app/models.py` | [models/RawLogEvent.yaml](models/RawLogEvent.yaml) |
| `OutboxEvent` | persistence-write | `command_service/app/models.py` | [models/OutboxEvent.yaml](models/OutboxEvent.yaml) |
| `User` | persistence-write | `command_service/app/models.py` | [models/User.yaml](models/User.yaml) |
| `AuthLoginCode` | persistence-write | `command_service/app/models.py` | [models/AuthLoginCode.yaml](models/AuthLoginCode.yaml) |
| `TournamentRecord` | persistence-write | `command_service/app/models.py` | [models/TournamentRecord.yaml](models/TournamentRecord.yaml) |
| `EventRecord` | persistence-write | `command_service/app/models.py` | [models/EventRecord.yaml](models/EventRecord.yaml) |
| `MatchSummaryProjection` | persistence-read | `query_service/app/models.py` | [models/MatchSummaryProjection.yaml](models/MatchSummaryProjection.yaml) |
| `TournamentSummaryProjection` | persistence-read | `query_service/app/models.py` | [models/TournamentSummaryProjection.yaml](models/TournamentSummaryProjection.yaml) |
| `EventSummaryProjection` | persistence-read | `query_service/app/models.py` | [models/EventSummaryProjection.yaml](models/EventSummaryProjection.yaml) |
| `EventPlayerStatsProjection` | persistence-read | `query_service/app/models.py` | [models/EventPlayerStatsProjection.yaml](models/EventPlayerStatsProjection.yaml) |
| `PlayerMatchStatsProjection` | persistence-read | `query_service/app/models.py` | [models/PlayerMatchStatsProjection.yaml](models/PlayerMatchStatsProjection.yaml) |
| `PlayerMatchClassStatsProjection` | persistence-read | `query_service/app/models.py` | [models/PlayerMatchClassStatsProjection.yaml](models/PlayerMatchClassStatsProjection.yaml) |
| `PlayerLifetimeStatsProjection` | persistence-read | `query_service/app/models.py` | [models/PlayerLifetimeStatsProjection.yaml](models/PlayerLifetimeStatsProjection.yaml) |
| `PlayerClassStatsProjection` | persistence-read | `query_service/app/models.py` | [models/PlayerClassStatsProjection.yaml](models/PlayerClassStatsProjection.yaml) |
| `ClassRatingBenchmarkProjection` | persistence-read | `query_service/app/models.py` | [models/ClassRatingBenchmarkProjection.yaml](models/ClassRatingBenchmarkProjection.yaml) |
| `PlayerIdentityProjection` | persistence-read | `query_service/app/models.py` | [models/PlayerIdentityProjection.yaml](models/PlayerIdentityProjection.yaml) |
| `LeaderboardSnapshotProjection` | persistence-read | `query_service/app/models.py` | [models/LeaderboardSnapshotProjection.yaml](models/LeaderboardSnapshotProjection.yaml) |
| `ProcessedEvent` | persistence-read | `query_service/app/models.py` | [models/ProcessedEvent.yaml](models/ProcessedEvent.yaml) |

## Kinds

| Kind | Description |
|------|-------------|
| `command` | HTTP request body accepted by the command service |
| `domain` | Normalized match/player payload carried in integration events |
| `view` | JSON returned by the query service (materialized read model) |
| `auth` | Authentication request/response DTOs |
| `response` | Command-side async acceptance envelope |
| `event` | RabbitMQ integration event envelope or payload |
| `persistence-write` | Command Postgres table (`cqrs_command`) |
| `persistence-read` | Query Postgres projection table (`cqrs_query`) |

## CDM file format

Each YAML file follows this structure:

```yaml
model: ModelName
kind: view
version: "1.0"
source: server/cqrs/shared/schemas.py
description: Human-readable purpose
fields:
  - name: field_name
    type: string
    required: true
    description: ...
constraints: []
relationships: []
```
