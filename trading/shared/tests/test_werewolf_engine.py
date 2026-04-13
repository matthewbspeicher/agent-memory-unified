"""Tests for the Werewolf escape room engine."""

import pytest
from competition.escape_rooms.werewolf import WerewolfEnvironment, WerewolfState


class TestWerewolfInitialization:
    """Test WerewolfEnvironment initialization."""

    def test_default_initialization(self):
        """Test default initialization with 10 agents."""
        env = WerewolfEnvironment()
        assert env.num_agents == 10
        assert env.state == WerewolfState.PRE_GAME
        assert len(env.alive_agents) == 10
        assert len(env.roles) == 10
        assert env.winner is None
        assert env.debate_round == 0

    def test_custom_agent_count(self):
        """Test initialization with custom agent count."""
        for n in [5, 8, 12, 15]:
            env = WerewolfEnvironment({"num_agents": n})
            assert env.num_agents == n
            assert len(env.alive_agents) == n
            assert len(env.roles) == n

    def test_night_actions_initialized(self):
        """Test night actions structure is properly initialized."""
        env = WerewolfEnvironment({"num_agents": 10})
        assert "kills" in env.night_actions
        assert "protected" in env.night_actions
        assert env.night_actions["kills"] == []
        assert env.night_actions["protected"] is None


class TestWerewolfRoleAssignment:
    """Test role assignment algorithm."""

    def test_werewolf_count_20_percent(self):
        """Test werewolves are approximately 20% of players."""
        test_cases = [
            (5, 1),  # floor(5 * 0.2) = 1
            (10, 2),  # floor(10 * 0.2) = 2
            (15, 3),  # floor(15 * 0.2) = 3
            (20, 4),  # floor(20 * 0.2) = 4
        ]
        for num_players, expected_wolves in test_cases:
            env = WerewolfEnvironment({"num_agents": num_players})
            wolf_count = sum(1 for role in env.roles.values() if role == "werewolf")
            assert wolf_count == expected_wolves, (
                f"Expected {expected_wolves} wolves for {num_players} players, got {wolf_count}"
            )

    def test_seer_assigned_at_6_players(self):
        """Test Seer is assigned when 6+ players."""
        # 5 players - no seer
        env_5 = WerewolfEnvironment({"num_agents": 5})
        assert "seer" not in env_5.roles.values()

        # 6 players - has seer
        env_6 = WerewolfEnvironment({"num_agents": 6})
        assert "seer" in env_6.roles.values()

        # 10 players - has seer
        env_10 = WerewolfEnvironment({"num_agents": 10})
        assert "seer" in env_10.roles.values()

    def test_doctor_assigned_at_8_players(self):
        """Test Doctor is assigned when 8+ players."""
        # 7 players - no doctor
        env_7 = WerewolfEnvironment({"num_agents": 7})
        assert "doctor" not in env_7.roles.values()

        # 8 players - has doctor
        env_8 = WerewolfEnvironment({"num_agents": 8})
        assert "doctor" in env_8.roles.values()

        # 12 players - has doctor
        env_12 = WerewolfEnvironment({"num_agents": 12})
        assert "doctor" in env_12.roles.values()

    def test_jester_assigned_at_10_players(self):
        """Test Jester is assigned when 10+ players."""
        # 9 players - no jester
        env_9 = WerewolfEnvironment({"num_agents": 9})
        assert "jester" not in env_9.roles.values()

        # 10 players - has jester
        env_10 = WerewolfEnvironment({"num_agents": 10})
        assert "jester" in env_10.roles.values()

        # 15 players - has jester
        env_15 = WerewolfEnvironment({"num_agents": 15})
        assert "jester" in env_15.roles.values()

    def test_villagers_fill_remaining(self):
        """Test villagers fill remaining slots after special roles."""
        # 10 players: 2 wolves + 1 seer + 1 doctor + 1 jester = 5 special, 5 villagers
        env = WerewolfEnvironment({"num_agents": 10})
        role_counts = {}
        for role in env.roles.values():
            role_counts[role] = role_counts.get(role, 0) + 1

        assert role_counts["werewolf"] == 2
        assert role_counts["seer"] == 1
        assert role_counts["doctor"] == 1
        assert role_counts["jester"] == 1
        assert role_counts["villager"] == 5
        assert sum(role_counts.values()) == 10

    def test_role_distribution_sum(self):
        """Test total roles always equals num_agents."""
        for n in [5, 7, 10, 12, 20]:
            env = WerewolfEnvironment({"num_agents": n})
            assert len(env.roles) == n

    def test_roles_are_valid(self):
        """Test all assigned roles are valid role types."""
        valid_roles = {"werewolf", "seer", "doctor", "jester", "villager"}
        for n in [5, 8, 10, 15]:
            env = WerewolfEnvironment({"num_agents": n})
            for role in env.roles.values():
                assert role in valid_roles, f"Invalid role: {role}"


class TestWerewolfFactoryIntegration:
    """Test werewolf integration with room factory."""

    def test_werewolf_registered_in_factory(self):
        """Test werewolf room type is registered in factory."""
        from competition.escape_rooms.factory import (
            create_room,
            get_available_room_types,
        )

        available_types = get_available_room_types()
        assert "werewolf" in available_types

    def test_create_werewolf_room(self):
        """Test creating werewolf room via factory."""
        from competition.escape_rooms.factory import create_room

        room = create_room("werewolf", {"num_agents": 8})
        assert isinstance(room, WerewolfEnvironment)
        assert room.num_agents == 8


class TestWerewolfNightPhase:
    """Test night phase tool logic."""

    def _get_env_with_roles(self, num_agents: int = 10):
        """Helper to create environment and find role holders."""
        env = WerewolfEnvironment({"num_agents": num_agents})
        env.state = WerewolfState.NIGHT

        role_holders = {"werewolf": [], "seer": None, "doctor": None}
        for agent_id, role in env.roles.items():
            if role == "werewolf":
                role_holders["werewolf"].append(agent_id)
            elif role == "seer":
                role_holders["seer"] = agent_id
            elif role == "doctor":
                role_holders["doctor"] = agent_id

        return env, role_holders

    @pytest.mark.asyncio
    async def test_werewolf_kill_success(self):
        """Test werewolf can successfully target a victim."""
        env, roles = self._get_env_with_roles(10)
        wolf = roles["werewolf"][0]
        target = 5 if wolf != 5 else 6

        result = await env.execute_tool("kill", {"agent_id": wolf, "target_id": target})
        assert "targeted" in result
        assert str(target) in result
        assert target in env.night_actions["kills"]

    @pytest.mark.asyncio
    async def test_werewolf_kill_not_werewolf(self):
        """Test non-werewolf cannot use kill."""
        env, roles = self._get_env_with_roles(10)
        seer = roles["seer"]
        target = 5

        result = await env.execute_tool("kill", {"agent_id": seer, "target_id": target})
        assert "Not allowed" in result
        assert "werewolf" in result.lower() or "werewolves" in result.lower()

    @pytest.mark.asyncio
    async def test_werewolf_kill_self_target(self):
        """Test werewolf cannot target themselves."""
        env, roles = self._get_env_with_roles(10)
        wolf = roles["werewolf"][0]

        result = await env.execute_tool("kill", {"agent_id": wolf, "target_id": wolf})
        assert "Error" in result
        assert "themselves" in result.lower()

    @pytest.mark.asyncio
    async def test_werewolf_kill_dead_target(self):
        """Test werewolf cannot target a dead agent."""
        env, roles = self._get_env_with_roles(10)
        wolf = roles["werewolf"][0]
        dead_agent = 5 if wolf != 5 else 6
        env.alive_agents.remove(dead_agent)

        result = await env.execute_tool(
            "kill", {"agent_id": wolf, "target_id": dead_agent}
        )
        assert "Error" in result
        assert "not alive" in result.lower()

    @pytest.mark.asyncio
    async def test_seer_inspect_werewolf(self):
        """Test seer can identify werewolves."""
        env, roles = self._get_env_with_roles(10)
        seer = roles["seer"]
        wolf = roles["werewolf"][0]

        result = await env.execute_tool(
            "inspect", {"agent_id": seer, "target_id": wolf}
        )
        assert result == "WEREWOLF"

    @pytest.mark.asyncio
    async def test_seer_inspect_villager(self):
        """Test seer identifies non-werewolves as villagers."""
        env, roles = self._get_env_with_roles(10)
        seer = roles["seer"]

        # Find a non-werewolf target
        for agent_id, role in env.roles.items():
            if role not in ("werewolf", "seer") and agent_id != seer:
                result = await env.execute_tool(
                    "inspect", {"agent_id": seer, "target_id": agent_id}
                )
                assert result == "VILLAGER"
                break

    @pytest.mark.asyncio
    async def test_seer_inspect_not_seer(self):
        """Test non-seer cannot use inspect."""
        env, roles = self._get_env_with_roles(10)
        wolf = roles["werewolf"][0]
        target = 5 if wolf != 5 else 6

        result = await env.execute_tool(
            "inspect", {"agent_id": wolf, "target_id": target}
        )
        assert "Not allowed" in result
        assert "seer" in result.lower()

    @pytest.mark.asyncio
    async def test_doctor_protect_success(self):
        """Test doctor can protect a player."""
        env, roles = self._get_env_with_roles(10)
        doctor = roles["doctor"]
        target = 5 if doctor != 5 else 6

        result = await env.execute_tool(
            "protect", {"agent_id": doctor, "target_id": target}
        )
        assert "protected" in result
        assert str(target) in result
        assert env.night_actions["protected"] == target

    @pytest.mark.asyncio
    async def test_doctor_protect_not_doctor(self):
        """Test non-doctor cannot use protect."""
        env, roles = self._get_env_with_roles(10)
        seer = roles["seer"]
        target = 5

        result = await env.execute_tool(
            "protect", {"agent_id": seer, "target_id": target}
        )
        assert "Not allowed" in result
        assert "doctor" in result.lower()

    @pytest.mark.asyncio
    async def test_night_tools_wrong_state(self):
        """Test night tools are not available in wrong state."""
        env, roles = self._get_env_with_roles(10)
        env.state = WerewolfState.DAY
        wolf = roles["werewolf"][0]
        target = 5

        result = await env.execute_tool("kill", {"agent_id": wolf, "target_id": target})
        assert "called kill" in result
        assert target not in env.night_actions["kills"]

    @pytest.mark.asyncio
    async def test_night_actions_reset_structure(self):
        """Test night_actions structure is properly maintained."""
        env, roles = self._get_env_with_roles(10)

        assert isinstance(env.night_actions["kills"], list)
        assert env.night_actions["protected"] is None

        # Perform actions
        wolf = roles["werewolf"][0]
        target1 = 3 if wolf != 3 else 4
        await env.execute_tool("kill", {"agent_id": wolf, "target_id": target1})

        doctor = roles["doctor"]
        target2 = 7 if doctor != 7 else 8
        await env.execute_tool("protect", {"agent_id": doctor, "target_id": target2})

        assert len(env.night_actions["kills"]) == 1
        assert env.night_actions["protected"] is not None


class TestWerewolfDayPhase:
    """Test day phase and moderator logic."""

    def test_phase_transition_sequence(self):
        """Test the progression from PRE_GAME to VOTE."""
        env = WerewolfEnvironment()
        assert env.state == WerewolfState.PRE_GAME

        env.next_phase()
        assert env.state == WerewolfState.NIGHT

        env.next_phase()
        assert env.state == WerewolfState.DAWN

        env.next_phase()
        assert env.state == WerewolfState.DAY
        assert env.debate_round == 0

        env.next_phase()
        assert env.state == WerewolfState.DAY
        assert env.debate_round == 1

        env.next_phase()
        assert env.state == WerewolfState.DAY
        assert env.debate_round == 2

        env.next_phase()
        assert env.state == WerewolfState.VOTE

    @pytest.mark.asyncio
    async def test_night_processing_kill(self):
        """Test that night processing correctly kills a target."""
        env = WerewolfEnvironment({"num_agents": 6})
        env.state = WerewolfState.NIGHT

        wolf_id = [i for i, r in env.roles.items() if r == "werewolf"][0]
        # Pick a target that is NOT the wolf
        target_id = [i for i in range(6) if i != wolf_id][0]

        await env.execute_tool("kill", {"agent_id": wolf_id, "target_id": target_id})

        env.next_phase()  # Transition to DAWN
        assert env.state == WerewolfState.DAWN
        assert target_id not in env.alive_agents
        assert "was found dead" in env.match_log[-1]

    @pytest.mark.asyncio
    async def test_night_processing_protection(self):
        """Test that doctor protection prevents death."""
        env = WerewolfEnvironment({"num_agents": 8})
        env.state = WerewolfState.NIGHT

        wolf_id = [i for i, r in env.roles.items() if r == "werewolf"][0]
        doctor_id = [i for i, r in env.roles.items() if r == "doctor"][0]
        target_id = [i for i in range(8) if i != wolf_id and i != doctor_id][0]

        await env.execute_tool("kill", {"agent_id": wolf_id, "target_id": target_id})
        await env.execute_tool(
            "protect", {"agent_id": doctor_id, "target_id": target_id}
        )

        env.next_phase()  # Transition to DAWN
        assert target_id in env.alive_agents
        assert "Night was quiet" in env.match_log[-1]

    @pytest.mark.asyncio
    async def test_day_suspicion_tool(self):
        """Test the state_suspicion tool during day phase."""
        env = WerewolfEnvironment()
        env.state = WerewolfState.DAY

        agent_id = env.alive_agents[0]
        target_id = env.alive_agents[1]

        result = await env.execute_tool(
            "state_suspicion",
            {"agent_id": agent_id, "target_id": target_id, "reason": "Shifty eyes."},
        )
        assert "recorded" in result
        assert "suspects" in env.match_log[-1]

    def test_moderator_prompt(self):
        """Test that moderator generates prompts during day."""
        env = WerewolfEnvironment()
        env.state = WerewolfState.DAY

        prompt = env.get_moderator_prompt()
        assert len(prompt) > 0
        assert "Agent" in prompt


class TestWerewolfVotingAndVictory:
    """Test voting and victory condition logic."""

    def _set_up_vote_state(self, num_agents: int = 10):
        """Helper to set up environment in VOTE state."""
        env = WerewolfEnvironment({"num_agents": num_agents})
        env.state = WerewolfState.VOTE
        return env

    def test_vote_eliminates_target(self):
        """Test that voting eliminates the top target."""
        env = self._set_up_vote_state(10)
        target = 5
        votes = {i: target for i in env.alive_agents}

        result = env.execute_vote(votes)
        assert target not in env.alive_agents
        assert "was executed" in result

    def test_vote_tie_no_elimination(self):
        """Test that tie votes result in no elimination."""
        env = self._set_up_vote_state(6)
        alive = env.alive_agents
        votes = {
            alive[0]: alive[1],
            alive[1]: alive[0],
            alive[2]: alive[3],
            alive[3]: alive[2],
        }

        result = env.execute_vote(votes)
        assert "Tie vote" in result
        assert len(env.alive_agents) == 6

    def test_vote_log_records_elimination(self):
        """Test that match_log records the elimination with role."""
        env = self._set_up_vote_state(10)
        target = 4
        votes = {i: target for i in env.alive_agents}
        target_role = env.roles[target]

        env.execute_vote(votes)
        assert any(f"Agent {target} was executed" in entry for entry in env.match_log)
        assert target_role in env.match_log[-1]

    def test_villagers_win_when_all_wolves_dead(self):
        """Test villagers win when all werewolves are eliminated."""
        env = self._set_up_vote_state(10)
        wolf_ids = [i for i, r in env.roles.items() if r == "werewolf"]
        for w in wolf_ids:
            env.alive_agents.remove(w)

        result = env._check_victory()
        assert result is True
        assert env.winner == "villagers"
        assert env.state == WerewolfState.POST_GAME

    def test_werewolves_win_whenwolves_equal_villagers(self):
        """Test werewolves win when their count >= non-wolf count."""
        env = self._set_up_vote_state(10)
        alive_wolves = [i for i in env.alive_agents if env.roles[i] == "werewolf"]
        alive_villagers = [i for i in env.alive_agents if env.roles[i] != "werewolf"]
        while len(alive_wolves) < len(alive_villagers):
            villager = alive_villagers.pop()
            env.alive_agents.remove(villager)

        result = env._check_victory()
        assert result is True
        assert env.winner == "werewolves"
        assert env.state == WerewolfState.POST_GAME

    def test_jester_wins_when_voted_out(self):
        """Test jester wins if eliminated by vote."""
        env = self._set_up_vote_state(10)
        jester_id = [i for i, r in env.roles.items() if r == "jester"][0]
        votes = {i: jester_id for i in env.alive_agents}

        result = env.execute_vote(votes)
        assert env.winner == "jester"
        assert env.state == WerewolfState.POST_GAME
        assert "Jester wins" in result

    def test_next_phase_transitions_to_post_game_on_victory(self):
        """Test next_phase transitions to POST_GAME when victory is detected."""
        env = self._set_up_vote_state(10)
        wolf_ids = [i for i, r in env.roles.items() if r == "werewolf"]
        for w in wolf_ids:
            env.alive_agents.remove(w)

        env.next_phase()
        assert env.state == WerewolfState.POST_GAME
        assert env.winner == "villagers"

    def test_next_phase_transitions_to_night_on_no_victory(self):
        """Test next_phase transitions back to NIGHT when no victory."""
        env = self._set_up_vote_state(10)
        # Keep all wolves alive, game not over

        env.next_phase()
        assert env.state == WerewolfState.NIGHT
        assert env.winner is None

    def test_vote_wrong_state_error(self):
        """Test voting returns error if not in VOTE state."""
        env = WerewolfEnvironment()
        env.state = WerewolfState.DAY
        votes = {0: 1}

        result = env.execute_vote(votes)
        assert "Error" in result
        assert "DAY" in result

    def test_vote_dead_voter_error(self):
        """Test voting returns error if voter is dead."""
        env = self._set_up_vote_state(10)
        dead_voter = env.alive_agents[0]
        env.alive_agents.remove(dead_voter)
        votes = {dead_voter: 1, env.alive_agents[0]: env.alive_agents[1]}

        result = env.execute_vote(votes)
        assert "Error" in result
        assert str(dead_voter) in result

    def test_verify_flag_returns_true_for_winner(self):
        """Test verify_flag returns True when flag matches winner."""
        env = self._set_up_vote_state(10)
        wolf_ids = [i for i, r in env.roles.items() if r == "werewolf"]
        for w in wolf_ids:
            env.alive_agents.remove(w)
        env._check_victory()

        assert env.verify_flag("villagers") is True
        assert env.verify_flag("werewolves") is False

    def test_verify_flag_returns_false_when_no_winner(self):
        """Test verify_flag returns False when game is not over."""
        env = WerewolfEnvironment()
        assert env.verify_flag("villagers") is False
        assert env.verify_flag("werewolves") is False


class TestWerewolfMetrics:
    """Test Theory of Mind and Deception metrics."""

    def test_metrics_initialized_in_constructor(self):
        """Test metrics dictionary is properly initialized."""
        env = WerewolfEnvironment()
        assert "perception_probes" in env.metrics
        assert "influence_events" in env.metrics
        assert "deception_spikes" in env.metrics
        assert isinstance(env.metrics["perception_probes"], list)
        assert isinstance(env.metrics["influence_events"], list)
        assert isinstance(env.metrics["deception_spikes"], list)

    def test_record_perception_probe_basic(self):
        """Test basic perception probe recording."""
        env = WerewolfEnvironment({"num_agents": 10})
        agent_id = 0
        prob_map = {i: 0.2 if i < 2 else 0.0 for i in range(10)}

        probe_score = env.record_perception_probe(agent_id, prob_map)

        assert probe_score > 0
        assert len(env.metrics["perception_probes"]) == 1
        assert env.metrics["perception_probes"][0]["agent_id"] == agent_id
        assert "probe_score" in env.metrics["perception_probes"][0]
        assert "timestamp" in env.metrics["perception_probes"][0]

    def test_record_perception_probe_perfect_werewolf_detection(self):
        """Test probe score is higher when probability map matches actual roles."""
        env = WerewolfEnvironment({"num_agents": 10})
        agent_id = 0

        perfect_map = {}
        for aid, role in env.roles.items():
            perfect_map[aid] = 1.0 if role == "werewolf" else 0.0

        perfect_score = env.record_perception_probe(agent_id, perfect_map)

        random_map = {i: 0.5 for i in range(10)}
        random_score = env.record_perception_probe(agent_id, random_map)

        assert perfect_score > random_score

    def test_record_perception_probe_stores_mse(self):
        """Test that MSE is stored with the probe."""
        env = WerewolfEnvironment({"num_agents": 10})
        agent_id = 0
        prob_map = {i: 0.0 for i in range(10)}

        env.record_perception_probe(agent_id, prob_map)

        assert "mse" in env.metrics["perception_probes"][0]
        assert env.metrics["perception_probes"][0]["mse"] >= 0

    def test_detect_deception_kill_vs_trust(self):
        """Test deception detection when thoughts say kill but action says trust."""
        env = WerewolfEnvironment({"num_agents": 10})
        agent_id = 0

        thoughts = "I think agent 5 is a werewolf. I will kill agent 5 tonight."
        public_action = "I trust agent 5. They seem innocent to me."

        detected = env.detect_deception(agent_id, thoughts, public_action)

        assert detected is True
        assert len(env.metrics["deception_spikes"]) == 1
        assert env.metrics["deception_spikes"][0]["agent_id"] == agent_id
        assert "thought_vs_action_delta" in env.metrics["deception_spikes"][0]

    def test_detect_deception_kill_vs_vote_innocent(self):
        """Test deception when thoughts plan kill but action votes innocent."""
        env = WerewolfEnvironment({"num_agents": 10})
        agent_id = 0

        thoughts = "Agent 3 is definitely a wolf. Must kill them."
        public_action = "I vote innocent on agent 3. No evidence against them."

        detected = env.detect_deception(agent_id, thoughts, public_action)

        assert detected is True

    def test_detect_deception_no_deception(self):
        """Test no deception spike when thoughts match actions."""
        env = WerewolfEnvironment({"num_agents": 10})
        agent_id = 0

        thoughts = "Agent 5 looks suspicious. I will vote for them."
        public_action = "I vote for agent 5. They seem suspicious."

        detected = env.detect_deception(agent_id, thoughts, public_action)

        assert detected is False
        assert len(env.metrics["deception_spikes"]) == 0

    def test_detect_deception_multiple_spikes(self):
        """Test multiple deception spikes are recorded."""
        env = WerewolfEnvironment({"num_agents": 10})

        thoughts1 = "Kill agent 5"
        action1 = "I trust agent 5"
        env.detect_deception(0, thoughts1, action1)

        thoughts2 = "Agent 7 is a wolf, must kill"
        action2 = "vote innocent on agent 7"
        env.detect_deception(1, thoughts2, action2)

        assert len(env.metrics["deception_spikes"]) == 2

    def test_calculate_influence_score_no_suspicions(self):
        """Test influence score is 0 when agent has no suspicions."""
        env = WerewolfEnvironment({"num_agents": 10})
        agent_id = 0

        score = env.calculate_influence_score(agent_id)

        assert score == 0.0

    def test_calculate_influence_score_with_suspicions_no_votes(self):
        """Test influence score is 0 when suspicions exist but no votes cast."""
        env = WerewolfEnvironment({"num_agents": 10})
        env.state = WerewolfState.DAY

        import asyncio

        asyncio.run(
            env.execute_tool(
                "state_suspicion",
                {"agent_id": 0, "target_id": 5, "reason": "Suspicious"},
            )
        )

        score = env.calculate_influence_score(0)

        assert score == 0.0

    def test_calculate_influence_score_with_suspicions_and_votes(self):
        """Test influence score when suspicions correlate with votes."""
        env = WerewolfEnvironment({"num_agents": 10})
        env.state = WerewolfState.DAY

        import asyncio

        asyncio.run(
            env.execute_tool(
                "state_suspicion",
                {"agent_id": 0, "target_id": 5, "reason": "Suspicious"},
            )
        )

        env.state = WerewolfState.VOTE
        env.execute_vote({0: 5, 1: 5, 2: 5, 3: 5, 4: 5, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0})

        score = env.calculate_influence_score(0)

        assert score > 0

    def test_vote_history_tracked(self):
        """Test that votes are tracked in vote history."""
        env = WerewolfEnvironment({"num_agents": 10})
        env.state = WerewolfState.VOTE

        votes = {i: 5 for i in env.alive_agents}
        env.execute_vote(votes)

        assert len(env._vote_history) == 1
        assert env._vote_history[0] == votes

    def test_suspicion_history_tracked(self):
        """Test that suspicions are tracked in history."""
        env = WerewolfEnvironment({"num_agents": 10})
        env.state = WerewolfState.DAY

        import asyncio

        asyncio.run(
            env.execute_tool(
                "state_suspicion",
                {"agent_id": 0, "target_id": 5, "reason": "Suspicious"},
            )
        )

        assert len(env._suspicion_history) == 1
        assert env._suspicion_history[0]["source_id"] == 0
        assert env._suspicion_history[0]["target_id"] == 5

    def test_metrics_persistence_across_phases(self):
        """Test that metrics persist across multiple phases."""
        env = WerewolfEnvironment({"num_agents": 10})

        env.record_perception_probe(0, {i: 0.1 for i in range(10)})

        env.state = WerewolfState.DAY
        import asyncio

        asyncio.run(
            env.execute_tool(
                "state_suspicion", {"agent_id": 0, "target_id": 5, "reason": "Test"}
            )
        )

        env.detect_deception(0, "Kill 5", "Trust 5")

        assert len(env.metrics["perception_probes"]) == 1
        assert len(env.metrics["influence_events"]) == 0
        assert len(env.metrics["deception_spikes"]) == 1
