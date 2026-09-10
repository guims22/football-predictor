import React, { useEffect, useState, useCallback } from "react";
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  ActivityIndicator,
  TouchableOpacity,
  RefreshControl,
  SafeAreaView,
  Image,
} from "react-native";
import { useRouter } from "expo-router";
import { getMatchesToday, getUpcomingMatches, Match } from "../../services/api";

const C = {
  bg: "#0a1628",
  card: "#1a2744",
  primary: "#00c853",
  accent: "#1565c0",
  text: "#ffffff",
  muted: "#8892a4",
  border: "#2d3748",
};

type Tab = "today" | "upcoming";

export default function MatchesScreen() {
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [tab, setTab] = useState<Tab>("today");
  const router = useRouter();

  const fetchMatches = useCallback(async () => {
    try {
      const res =
        tab === "today"
          ? await getMatchesToday()
          : await getUpcomingMatches(7);
      setMatches(res.data.matches || []);
    } catch {
      setMatches([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [tab]);

  useEffect(() => {
    setLoading(true);
    fetchMatches();
  }, [fetchMatches]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchMatches();
  };

  const formatTime = (utcDate: string) => {
    const d = new Date(utcDate);
    return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  };

  const formatDate = (utcDate: string) => {
    const d = new Date(utcDate);
    return d.toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" });
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "FINISHED": return { label: "Terminé", color: C.muted };
      case "IN_PLAY": return { label: "En cours", color: "#ff6b35" };
      case "TIMED":
      case "SCHEDULED": return { label: "Prévu", color: C.primary };
      default: return { label: status, color: C.muted };
    }
  };

  const renderMatch = ({ item }: { item: Match }) => {
    const badge = getStatusBadge(item.status);
    const isFinished = item.status === "FINISHED";

    return (
      <TouchableOpacity
        style={styles.card}
        onPress={() =>
          router.push({
            pathname: "/(tabs)/predictions",
            params: {
              matchId: item.id,
              homeId: item.homeTeam.id,
              awayId: item.awayTeam.id,
              homeName: item.homeTeam.name,
              awayName: item.awayTeam.name,
              competition: item.competition.name,
              // Sans le code de ligue, le backend ne peut recuperer ni les cotes
              // ni le classement : les deux passaient silencieusement a la trappe.
              competitionCode: item.competition.code ?? "",
              matchDate: item.utcDate,
            },
          })
        }
        activeOpacity={0.8}
      >
        <View style={styles.cardHeader}>
          {item.competition.emblem ? (
            <Image source={{ uri: item.competition.emblem }} style={styles.compLogo} />
          ) : null}
          <Text style={styles.compName} numberOfLines={1}>
            {item.competition.name}
          </Text>
          <View style={[styles.badge, { backgroundColor: badge.color + "22" }]}>
            <Text style={[styles.badgeText, { color: badge.color }]}>{badge.label}</Text>
          </View>
        </View>

        <View style={styles.teamsRow}>
          <View style={styles.teamCol}>
            {item.homeTeam.crest ? (
              <Image source={{ uri: item.homeTeam.crest }} style={styles.crest} />
            ) : null}
            <Text style={styles.teamName} numberOfLines={2}>
              {item.homeTeam.shortName || item.homeTeam.name}
            </Text>
          </View>

          <View style={styles.scoreBox}>
            {isFinished ? (
              <Text style={styles.score}>
                {item.score.fullTime.home} - {item.score.fullTime.away}
              </Text>
            ) : (
              <Text style={styles.matchTime}>{formatTime(item.utcDate)}</Text>
            )}
            {!isFinished && (
              <Text style={styles.matchDate}>{formatDate(item.utcDate)}</Text>
            )}
          </View>

          <View style={[styles.teamCol, { alignItems: "flex-end" }]}>
            {item.awayTeam.crest ? (
              <Image source={{ uri: item.awayTeam.crest }} style={styles.crest} />
            ) : null}
            <Text style={[styles.teamName, { textAlign: "right" }]} numberOfLines={2}>
              {item.awayTeam.shortName || item.awayTeam.name}
            </Text>
          </View>
        </View>

        <View style={styles.predictBtn}>
          <Text style={styles.predictBtnText}>Voir la prédiction IA →</Text>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>⚽ Football Predictor</Text>
        <Text style={styles.headerSub}>Propulsé par Claude AI</Text>
      </View>

      <View style={styles.tabs}>
        {(["today", "upcoming"] as Tab[]).map((t) => (
          <TouchableOpacity
            key={t}
            style={[styles.tab, tab === t && styles.tabActive]}
            onPress={() => setTab(t)}
          >
            <Text style={[styles.tabText, tab === t && styles.tabTextActive]}>
              {t === "today" ? "Aujourd'hui" : "À venir"}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={C.primary} />
          <Text style={styles.loadingText}>Chargement des matchs...</Text>
        </View>
      ) : matches.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.emptyText}>Aucun match disponible</Text>
        </View>
      ) : (
        <FlatList
          data={matches}
          keyExtractor={(item) => item.id.toString()}
          renderItem={renderMatch}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.primary} />
          }
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: C.bg },
  header: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 8 },
  headerTitle: { color: C.text, fontSize: 22, fontWeight: "800" },
  headerSub: { color: C.muted, fontSize: 12, marginTop: 2 },
  tabs: { flexDirection: "row", marginHorizontal: 20, marginVertical: 10, backgroundColor: C.card, borderRadius: 10, padding: 3 },
  tab: { flex: 1, paddingVertical: 8, alignItems: "center", borderRadius: 8 },
  tabActive: { backgroundColor: C.primary },
  tabText: { color: C.muted, fontWeight: "600", fontSize: 13 },
  tabTextActive: { color: "#000" },
  list: { paddingHorizontal: 16, paddingBottom: 20 },
  card: { backgroundColor: C.card, borderRadius: 16, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border },
  cardHeader: { flexDirection: "row", alignItems: "center", marginBottom: 14 },
  compLogo: { width: 18, height: 18, marginRight: 6 },
  compName: { flex: 1, color: C.muted, fontSize: 12, fontWeight: "600" },
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 20 },
  badgeText: { fontSize: 11, fontWeight: "700" },
  teamsRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  teamCol: { flex: 2, alignItems: "flex-start" },
  crest: { width: 36, height: 36, marginBottom: 6 },
  teamName: { color: C.text, fontSize: 13, fontWeight: "700", lineHeight: 18 },
  scoreBox: { flex: 1.5, alignItems: "center" },
  score: { color: C.text, fontSize: 22, fontWeight: "800" },
  matchTime: { color: C.primary, fontSize: 18, fontWeight: "800" },
  matchDate: { color: C.muted, fontSize: 11, marginTop: 2 },
  predictBtn: { marginTop: 14, paddingTop: 12, borderTopWidth: 1, borderTopColor: C.border, alignItems: "center" },
  predictBtnText: { color: C.primary, fontSize: 13, fontWeight: "700" },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  loadingText: { color: C.muted, marginTop: 12 },
  emptyText: { color: C.muted, fontSize: 16 },
});
