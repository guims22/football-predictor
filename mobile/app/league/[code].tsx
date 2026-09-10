/**
 * Detail d'une competition : classement + matchs.
 *
 * Cet ecran n'existait pas. L'onglet Ligues renvoyait vers "/(tabs)/index" en
 * passant `competitionCode`, mais l'ecran d'accueil ne lit aucun parametre :
 * taper un championnat ne faisait donc rien. Les endpoints /leagues/{code}/standings
 * et /matches/competition/{code} n'etaient appeles nulle part.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Image,
  RefreshControl,
  SafeAreaView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import {
  describeError,
  getCompetitionMatches,
  getStandings,
  paramsFromMatch,
  Match,
  StandingBlock,
  StandingsResponse,
} from "../../services/api";

const C = {
  bg: "#0a1628",
  card: "#1a2744",
  primary: "#00c853",
  text: "#ffffff",
  muted: "#8892a4",
  border: "#2d3748",
  danger: "#ff5252",
};

type Tab = "classement" | "matchs";

export default function LeagueScreen() {
  const { code, name } = useLocalSearchParams<{ code: string; name?: string }>();
  const router = useRouter();

  const [tab, setTab] = useState<Tab>("classement");
  const [standings, setStandings] = useState<StandingsResponse | null>(null);
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!code) return;
    setError(null);
    try {
      if (tab === "classement") {
        const res = await getStandings(code);
        setStandings(res.data);
      } else {
        const res = await getCompetitionMatches(code);
        setMatches(res.data.matches || []);
      }
    } catch (e) {
      // On affiche la vraie raison au lieu d'une liste vide muette.
      setError(describeError(e));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [code, tab]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  const onRefresh = () => {
    setRefreshing(true);
    load();
  };

  const title = standings?.competition?.name || name || code || "Competition";

  const renderRow = ({ item }: { item: any }) => (
    <View style={s.row}>
      <Text style={[s.pos, item.position <= 4 && s.posTop]}>{item.position}</Text>
      {item.team?.crest ? (
        <Image source={{ uri: item.team.crest }} style={s.crest} />
      ) : (
        <View style={s.crest} />
      )}
      <Text style={s.teamName} numberOfLines={1}>
        {item.team?.shortName || item.team?.name}
      </Text>
      <Text style={s.stat}>{item.playedGames}</Text>
      <Text style={s.statDim}>
        {item.won}-{item.draw}-{item.lost}
      </Text>
      <Text style={s.stat}>
        {item.goalDifference > 0 ? "+" : ""}
        {item.goalDifference}
      </Text>
      <Text style={s.points}>{item.points}</Text>
    </View>
  );

  const renderMatch = ({ item }: { item: Match }) => {
    const done = item.status === "FINISHED";
    const d = new Date(item.utcDate);
    return (
      <TouchableOpacity
        style={s.matchCard}
        activeOpacity={0.8}
        onPress={() =>
          router.push({ pathname: "/(tabs)/predictions", params: paramsFromMatch(item) as any })
        }
      >
        <View style={s.matchTop}>
          <Text style={s.matchDate}>
            {d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" })} ·{" "}
            {d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
          </Text>
          <Text style={[s.badge, done && s.badgeDone]}>{done ? "Termine" : "A venir"}</Text>
        </View>
        <View style={s.matchTeams}>
          <Text style={s.matchTeam} numberOfLines={1}>
            {item.homeTeam.shortName || item.homeTeam.name}
          </Text>
          <Text style={s.matchScore}>
            {done
              ? `${item.score.fullTime.home} - ${item.score.fullTime.away}`
              : "vs"}
          </Text>
          <Text style={[s.matchTeam, { textAlign: "right" }]} numberOfLines={1}>
            {item.awayTeam.shortName || item.awayTeam.name}
          </Text>
        </View>
        {!done && <Text style={s.predictLink}>Voir la prediction IA →</Text>}
      </TouchableOpacity>
    );
  };

  const blocks: StandingBlock[] = standings?.standings || [];

  return (
    <SafeAreaView style={s.container}>
      <Stack.Screen options={{ title }} />

      <View style={s.header}>
        {standings?.competition?.emblem ? (
          <Image source={{ uri: standings.competition.emblem }} style={s.headerEmblem} />
        ) : null}
        <View style={{ flex: 1 }}>
          <Text style={s.headerTitle} numberOfLines={1}>{title}</Text>
          {standings?.area?.name ? (
            <Text style={s.headerSub}>{standings.area.name}</Text>
          ) : null}
        </View>
      </View>

      <View style={s.tabs}>
        {(["classement", "matchs"] as Tab[]).map((t) => (
          <TouchableOpacity
            key={t}
            style={[s.tab, tab === t && s.tabActive]}
            onPress={() => setTab(t)}
            activeOpacity={0.8}
          >
            <Text style={[s.tabText, tab === t && s.tabTextActive]}>
              {t === "classement" ? "Classement" : "Matchs"}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? (
        <View style={s.center}>
          <ActivityIndicator size="large" color={C.primary} />
        </View>
      ) : error ? (
        <View style={s.center}>
          <Text style={s.errorText}>{error}</Text>
          <TouchableOpacity style={s.retry} onPress={onRefresh} activeOpacity={0.8}>
            <Text style={s.retryText}>Reessayer</Text>
          </TouchableOpacity>
        </View>
      ) : tab === "classement" ? (
        blocks.length === 0 ? (
          <View style={s.center}>
            <Text style={s.muted}>Classement indisponible pour cette competition.</Text>
          </View>
        ) : (
          <FlatList
            data={blocks}
            keyExtractor={(_, i) => `bloc-${i}`}
            refreshControl={
              <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.primary} />
            }
            contentContainerStyle={s.list}
            renderItem={({ item }) => (
              <View style={s.block}>
                {item.group ? <Text style={s.groupTitle}>{item.group}</Text> : null}
                <View style={s.headRow}>
                  <Text style={s.headPos}>#</Text>
                  <Text style={s.headTeam}>Equipe</Text>
                  <Text style={s.headStat}>J</Text>
                  <Text style={s.headStatWide}>V-N-D</Text>
                  <Text style={s.headStat}>Diff</Text>
                  <Text style={s.headPts}>Pts</Text>
                </View>
                {item.table.map((r) => (
                  <View key={r.team.id}>{renderRow({ item: r })}</View>
                ))}
              </View>
            )}
          />
        )
      ) : matches.length === 0 ? (
        <View style={s.center}>
          <Text style={s.muted}>Aucun match sur la periode.</Text>
        </View>
      ) : (
        <FlatList
          data={matches}
          keyExtractor={(m) => m.id.toString()}
          renderItem={renderMatch}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.primary} />
          }
          contentContainerStyle={s.list}
        />
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: C.bg },
  center: { flex: 1, justifyContent: "center", alignItems: "center", padding: 24 },
  muted: { color: C.muted, fontSize: 14, textAlign: "center" },
  errorText: { color: C.danger, fontSize: 14, textAlign: "center", marginBottom: 14 },
  retry: { backgroundColor: C.primary, paddingHorizontal: 22, paddingVertical: 10, borderRadius: 10 },
  retryText: { color: "#04220f", fontWeight: "800" },

  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: 18, paddingTop: 14, paddingBottom: 6 },
  headerEmblem: { width: 34, height: 34, marginRight: 12, borderRadius: 6 },
  headerTitle: { color: C.text, fontSize: 19, fontWeight: "800" },
  headerSub: { color: C.muted, fontSize: 12, marginTop: 2 },

  tabs: { flexDirection: "row", backgroundColor: C.card, margin: 16, borderRadius: 12, padding: 4 },
  tab: { flex: 1, paddingVertical: 10, borderRadius: 9, alignItems: "center" },
  tabActive: { backgroundColor: C.primary },
  tabText: { color: C.muted, fontWeight: "700", fontSize: 13 },
  tabTextActive: { color: "#04220f" },

  list: { paddingHorizontal: 12, paddingBottom: 24 },
  block: { backgroundColor: C.card, borderRadius: 14, padding: 10, marginBottom: 14, borderWidth: 1, borderColor: C.border },
  groupTitle: { color: C.primary, fontWeight: "800", fontSize: 13, marginBottom: 8, marginLeft: 4 },

  headRow: { flexDirection: "row", alignItems: "center", paddingBottom: 8, marginBottom: 4, borderBottomWidth: 1, borderBottomColor: C.border },
  headPos: { width: 22, color: C.muted, fontSize: 11, fontWeight: "700" },
  headTeam: { flex: 1, marginLeft: 30, color: C.muted, fontSize: 11, fontWeight: "700" },
  headStat: { width: 34, textAlign: "center", color: C.muted, fontSize: 11, fontWeight: "700" },
  headStatWide: { width: 58, textAlign: "center", color: C.muted, fontSize: 11, fontWeight: "700" },
  headPts: { width: 34, textAlign: "center", color: C.muted, fontSize: 11, fontWeight: "700" },

  row: { flexDirection: "row", alignItems: "center", paddingVertical: 7 },
  pos: { width: 22, color: C.muted, fontSize: 12, fontWeight: "700" },
  posTop: { color: C.primary },
  crest: { width: 22, height: 22, marginRight: 8 },
  teamName: { flex: 1, color: C.text, fontSize: 13, fontWeight: "600" },
  stat: { width: 34, textAlign: "center", color: C.text, fontSize: 12 },
  statDim: { width: 58, textAlign: "center", color: C.muted, fontSize: 12 },
  points: { width: 34, textAlign: "center", color: C.primary, fontSize: 14, fontWeight: "800" },

  matchCard: { backgroundColor: C.card, borderRadius: 14, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: C.border },
  matchTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 10 },
  matchDate: { color: C.muted, fontSize: 12 },
  badge: { color: C.primary, fontSize: 11, fontWeight: "700", borderWidth: 1, borderColor: C.primary, borderRadius: 20, paddingHorizontal: 10, paddingVertical: 2 },
  badgeDone: { color: C.muted, borderColor: C.border },
  matchTeams: { flexDirection: "row", alignItems: "center" },
  matchTeam: { flex: 1, color: C.text, fontSize: 14, fontWeight: "700" },
  matchScore: { color: C.primary, fontSize: 15, fontWeight: "800", marginHorizontal: 10 },
  predictLink: { color: C.primary, fontSize: 13, fontWeight: "700", textAlign: "center", marginTop: 12, borderTopWidth: 1, borderTopColor: C.border, paddingTop: 10 },
});
