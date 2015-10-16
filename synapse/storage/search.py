# -*- coding: utf-8 -*-
# Copyright 2015 OpenMarket Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from twisted.internet import defer

from _base import SQLBaseStore
from synapse.storage.engines import PostgresEngine, Sqlite3Engine


class SearchStore(SQLBaseStore):
    @defer.inlineCallbacks
    def search_msgs(self, room_ids, search_term, keys):
        """Performs a full text search over events with give keys.

        Args:
            room_ids (list): List of room ids to search in
            search_term (str): Search term to search for
            keys (list): List of keys to search in, currently supports
                "content.body", "content.name", "content.body"

        Returns:
            2-tuple of (dict event_id -> rank, dict event_id -> event)
        """
        clauses = []
        args = []

        clauses.append(
            "room_id IN (%s)" % (",".join(["?"] * len(room_ids)),)
        )
        args.extend(room_ids)

        local_clauses = []
        for key in keys:
            local_clauses.append("key = ?")
            args.append(key)

        clauses.append(
            "(%s)" % (" OR ".join(local_clauses),)
        )

        if isinstance(self.database_engine, PostgresEngine):
            sql = (
                "SELECT ts_rank_cd(vector, query) AS rank, event_id"
                " FROM plainto_tsquery('english', ?) as query, event_search"
                " WHERE vector @@ query"
            )
        elif isinstance(self.database_engine, Sqlite3Engine):
            sql = (
                "SELECT 0 as rank, event_id FROM event_search"
                " WHERE value MATCH ?"
            )
        else:
            # This should be unreachable.
            raise Exception("Unrecognized database engine")

        for clause in clauses:
            sql += " AND " + clause

        # We add an arbitrary limit here to ensure we don't try to pull the
        # entire table from the database.
        sql += " ORDER BY rank DESC LIMIT 500"

        results = yield self._execute(
            "search_msgs", self.cursor_to_dict, sql, *([search_term] + args)
        )

        events = yield self._get_events([r["event_id"] for r in results])

        event_map = {
            ev.event_id: ev
            for ev in events
        }

        defer.returnValue((
            {
                r["event_id"]: r["rank"]
                for r in results
                if r["event_id"] in event_map
            },
            event_map
        ))
