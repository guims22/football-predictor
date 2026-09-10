import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  SafeAreaView,
  TouchableOpacity,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import {
  getFullPrediction,
  describeError,
  FullPrediction,
  TeamForm,
} from "../../services/api";

const C = {
  bg: "#0a1628",
  card: "#1a2744",
  primary: "#00c853",
  accent: "#1565c0",
  text: "#ffffff",
  muted: "#8892a4",
  border: "#2d3748",
  win: "#00c853",
  draw: "#f59e0b",
  loss: "#ef4444",
};

function ProbBar({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.round(value * 100);
  return (
    <View style={pb.wrap}>
      <Text style={pb.label}>{label}</Text>
      <View style={pb.track}>
        <View style={[pb.fill, { width: `${pct}%`, backgroundColor: color }]} />
      </View>
      <Text style={[pb.pct, { color }]}>{pct}%</Text>
    </View>
  );
}

const pb = StyleSheet.create({
  wrap: { marginBottom: 12 },
  label: { color: "#8892a4", fontSize: 12, marginBottom: 4 },
  track: { height: 10, backgroundColor: "#2d3748", borderRadius: 5, overflow: "hidden" },
  fill: { height: "100%", borderRadius: 5 },
  pct: { fontSize: 13, fontWeight: "700", marginTop: 3, textAlign: "right" },
});

function FormRow({ form, label }: { form: TeamForm; label: string }) {
  const dots = [
    ...Array(form.wins).fill("W"),
    ...Array(form.draws).fill("D"),
    ...Array(form.losses).fill("L"),
  ].slice(-5);

  return (
    <View style={fr.row}>
      <Text style={fr.teamLabel} numberOfLines={1}>{label}</Text>
      <View style={fr.dots}>
        {dots.map((r, i) => (
          <View
            key={i}
            style={[fr.dot, { backgroundColor: r === "W" ? C.win : r === "D" ? C.draw : C.loss }]}
          >
            <Text style={fr.dotText}>{r}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const fr = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", marginBottom: 8 },
  teamLabel: { width: 110, color: C.text, fontSize: 12, fontWeight: "600" },
  dots: { flexDirection: "row", gap: 5 },
  dot: { width: 24, height: 24, borderRadius: 12, justifyContent: "center", alignItems: "center" },
  dotText: { color: "#fff", fontSize: 10, fontWeight: "700" },
});

export default function PredictionsScreen() {
  const params = useLocalSearchParams<{
    matchId: string;
    homeId: string;
    awayId: string;
    homeName: string;
    awayName: string;
    competition: string;
    competitionCode: string;
    matchDate: string;
  }>();

  const [data, setData] = useState<FullPrediction | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasParams = params.matchId && params.homeId && params.awayId;

  const fetchPrediction = async () => {
    if (!hasParams) return;
    setLoading(true);
    setError(null);
    try {
      const res = await getFullPrediction({
        match_id: Number(params.matchId),
        home_team_id: Number(params.homeId),
        away_team_id: Number(params.awayId),
        home_team_name: params.homeName!,
        away_team_name: params.awayName!,
        competition: params.competition || "",
        competition_code: params.competitionCode || "",
        match_date: params.matchDate || "",
      });
      setData(res.data);
    } catch (e: any) {
      setError(describeError(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPrediction();
  }, [params.matchId]);

  if (!hasParams) {
    return (
      <SafeAreaView style={s.container}>
        <View style={s.center}>
          <Text style={s.emptyIcon}>📊</Text>
          <Text style={s.emptyTitle}>Aucun match sélectionné</Text>
          <Text style={s.emptyText}>
            Va dans l'onglet Matchs et appuie sur "Voir la prédiction IA"
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.container}>
      <View style={s.header}>
        <Text style={s.headerTitle}>Prédiction IA</Text>
        <Text style={s.headerSub}>{params.competition}</Text>
      </View>

      {loading ? (
        <View style={s.center}>
          <ActivityIndicator size="large" color={C.primary} />
          <Text style={s.loadingText}>Analyse en cours avec Claude AI...</Text>
        </View>
      ) : error ? (
        <View style={s.center}>
          <Text style={s.errorText}>{error}</Text>
          <TouchableOpacity style={s.retryBtn} onPress={fetchPrediction}>
            <Text style={s.retryText}>Réessayer</Text>
          </TouchableOpacity>
        </View>
      ) : data ? (
        <ScrollView contentContainerStyle={s.scroll}>
          {/* Match Header */}
          <View style={s.matchHeader}>
            <Text style={s.teamName}>{data.home_team}</Text>
            <View style={s.vsBox}>
              <Text style={s.predicted}>{data.prediction.predicted_score}</Text>
              <Text style={s.vsSub}>Score prédit</Text>
            </View>
            <Text style={[s.teamName, { textAlign: "right" }]}>{data.away_team}</Text>
          </View>

          {/* Confidence */}
          <View style={s.confidenceBox}>
            <Text style={s.confidenceLabel}>Confiance de l'IA</Text>
            <View style={{ alignItems: "flex-end" }}>
              <Text style={s.confidenceValue}>{data.prediction.confidence}%</Text>
              <Text style={s.methodText}>{data.prediction.method}</Text>
            </View>
          </View>

          {/* Probabilities */}
          <View style={s.card}>
            <Text style={s.cardTitle}>Probabilités</Text>
            <ProbBar label={`Victoire ${data.home_team}`} value={data.prediction.home_win} color={C.win} />
            <ProbBar label="Match nul" value={data.prediction.draw} color={C.draw} />
            <ProbBar label={`Victoire ${data.away_team}`} value={data.prediction.away_win} color={C.loss} />
          </View>

          {/* Form */}
          <View style={s.card}>
            <Text style={s.cardTitle}>Forme récente (5 matchs)</Text>
            <FormRow form={data.home_form} label={data.home_team} />
            <FormRow form={data.away_form} label={data.away_team} />
            <View style={s.statsGrid}>
              {[
                { label: "Buts marqués", home: data.home_form.avg_goals_scored, away: data.away_form.avg_goals_scored },
                { label: "Buts encaissés", home: data.home_form.avg_goals_conceded, away: data.away_form.avg_goals_conceded },
              ].map((stat) => (
                <View key={stat.label} style={s.statRow}>
                  <Text style={s.statValue}>{stat.home}</Text>
                  <Text style={s.statLabel}>{stat.label}</Text>
                  <Text style={s.statValue}>{stat.away}</Text>
                </View>
              ))}
            </View>
          </View>

          {/* H2H */}
          <View style={s.card}>
            <Text style={s.cardTitle}>Confrontations directes</Text>
            <View style={s.h2hRow}>
              <View style={s.h2hItem}>
                <Text style={[s.h2hVal, { color: C.win }]}>{data.h2h.home_wins}</Text>
                <Text style={s.h2hLabel}>{data.home_team}</Text>
              </View>
              <View style={s.h2hItem}>
                <Text style={[s.h2hVal, { color: C.draw }]}>{data.h2h.draws}</Text>
                <Text style={s.h2hLabel}>Nuls</Text>
              </View>
              <View style={s.h2hItem}>
                <Text style={[s.h2hVal, { color: C.loss }]}>{data.h2h.away_wins}</Text>
                <Text style={s.h2hLabel}>{data.away_team}</Text>
              </View>
            </View>
          </View>


          {/* Types de paris -- calcules par le backend, jamais affiches jusqu'ici */}
          <View style={s.card}>
            <Text style={s.cardTitle}>Autres paris</Text>
            <View style={s.betGrid}>
              {[
                { l: "Les deux marquent", v: data.prediction.btts },
                { l: "Plus de 1,5 but", v: data.prediction.over_1_5 },
                { l: "Plus de 2,5 buts", v: data.prediction.over_2_5 },
                { l: "Plus de 3,5 buts", v: data.prediction.over_3_5 },
              ].map((b) => (
                <View key={b.l} style={s.betItem}>
                  <Text style={[s.betPct, b.v >= 0.6 && { color: C.win }]}>
                    {Math.round(b.v * 100)}%
                  </Text>
                  <Text style={s.betLabel}>{b.l}</Text>
                </View>
              ))}
            </View>
            <Text style={s.xgLine}>
              Buts attendus : {data.home_team} {data.prediction.home_xg} · {data.away_team}{" "}
              {data.prediction.away_xg}
            </Text>
          </View>

          {/* Analyse de value : ecart entre notre probabilite et celle du marche.
              C'est la seule information reellement exploitable pour parier --
              suivre le marche ne bat jamais le marche. */}
          {data.prediction.value_analysis ? (
            <View style={s.card}>
              <Text style={s.cardTitle}>Value contre les bookmakers</Text>
              {(
                [
                  ["home_win", `Victoire ${data.home_team}`],
                  ["draw", "Match nul"],
                  ["away_win", `Victoire ${data.away_team}`],
                ] as const
              ).map(([k, label]) => {
                const v = data.prediction.value_analysis?.[k];
                if (!v) return null;
                const positive = v.edge > 0;
                return (
                  <View key={k} style={s.valueRow}>
                    <Text style={s.valueLabel} numberOfLines={1}>{label}</Text>
                    <Text style={s.valueCell}>{Math.round(v.model_prob * 100)}%</Text>
                    <Text style={s.valueCellDim}>{Math.round(v.market_prob * 100)}%</Text>
                    <Text style={[s.valueEdge, { color: positive ? C.win : C.muted }]}>
                      {positive ? "+" : ""}
                      {Math.round(v.edge * 100)} pts
                    </Text>
                    {v.value_bet ? <Text style={s.valueFlag}>VALUE</Text> : null}
                  </View>
                );
              })}
              <View style={s.valueLegend}>
                <Text style={s.valueLegendText}>
                  Colonnes : notre probabilite · celle du marche · ecart. Un ecart positif
                  signale un pari potentiellement sous-cote. Ce n'est pas une garantie de gain.
                </Text>
              </View>
            </View>
          ) : null}

          {/* Classement : le backend le calculait deja, il n'etait jamais montre */}
          {data.standings &&
          (data.standings.home_position || data.standings.away_position) ? (
            <View style={s.card}>
              <Text style={s.cardTitle}>Classement</Text>
              <View style={s.h2hRow}>
                <View style={s.h2hItem}>
                  <Text style={[s.h2hVal, { color: C.primary }]}>
                    {data.standings.home_position ?? "-"}
                  </Text>
                  <Text style={s.h2hLabel} numberOfLines={1}>{data.home_team}</Text>
                </View>
                <View style={s.h2hItem}>
                  <Text style={[s.h2hVal, { color: C.primary }]}>
                    {data.standings.away_position ?? "-"}
                  </Text>
                  <Text style={s.h2hLabel} numberOfLines={1}>{data.away_team}</Text>
                </View>
              </View>
            </View>
          ) : null}

          {/* Claude Analysis */}
          <View style={[s.card, s.analysisCard]}>
            <View style={s.analysisHeader}>
              <Text style={s.analysisIcon}>✨</Text>
              <Text style={s.cardTitle}>Analyse Claude AI</Text>
            </View>
            <Text style={s.analysisText}>{data.analysis}</Text>
          </View>
        </ScrollView>
      ) : null}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: C.bg },
  header: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 8 },
  headerTitle: { color: C.text, fontSize: 22, fontWeight: "800" },
  headerSub: { color: C.muted, fontSize: 12, marginTop: 2 },
  scroll: { paddingHorizontal: 16, paddingBottom: 24 },
  center: { flex: 1, justifyContent: "center", alignItems: "center", padding: 32 },
  loadingText: { color: C.muted, marginTop: 16, textAlign: "center" },
  errorText: { color: C.loss, textAlign: "center", marginBottom: 16 },
  retryBtn: { backgroundColor: C.accent, paddingHorizontal: 24, paddingVertical: 10, borderRadius: 8 },
  retryText: { color: C.text, fontWeight: "700" },
  emptyIcon: { fontSize: 48, marginBottom: 16 },
  emptyTitle: { color: C.text, fontSize: 18, fontWeight: "700", marginBottom: 8 },
  emptyText: { color: C.muted, textAlign: "center", fontSize: 14, lineHeight: 20 },
  matchHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: C.card, borderRadius: 16, padding: 20, marginBottom: 12, borderWidth: 1, borderColor: C.border },
  teamName: { flex: 1, color: C.text, fontSize: 14, fontWeight: "700" },
  vsBox: { flex: 1, alignItems: "center" },
  predicted: { color: C.primary, fontSize: 26, fontWeight: "900" },
  vsSub: { color: C.muted, fontSize: 10, marginTop: 2 },
  confidenceBox: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", backgroundColor: C.accent + "33", borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1, borderColor: C.accent + "66" },
  confidenceLabel: { color: C.text, fontWeight: "600" },
  confidenceValue: { color: C.primary, fontSize: 20, fontWeight: "900" },
  betGrid: { flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between" },
  betItem: { width: "48%", backgroundColor: C.bg, borderRadius: 12, paddingVertical: 12, alignItems: "center", marginBottom: 8, borderWidth: 1, borderColor: C.border },
  betPct: { color: C.text, fontSize: 18, fontWeight: "800" },
  betLabel: { color: C.muted, fontSize: 11, marginTop: 3, textAlign: "center" },
  xgLine: { color: C.muted, fontSize: 11, textAlign: "center", marginTop: 6 },
  valueRow: { flexDirection: "row", alignItems: "center", paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: C.border },
  valueLabel: { flex: 1, color: C.text, fontSize: 12, fontWeight: "600" },
  valueCell: { width: 46, textAlign: "center", color: C.text, fontSize: 12, fontWeight: "700" },
  valueCellDim: { width: 46, textAlign: "center", color: C.muted, fontSize: 12 },
  valueEdge: { width: 62, textAlign: "right", fontSize: 12, fontWeight: "700" },
  valueFlag: { marginLeft: 6, color: "#04220f", backgroundColor: C.win, fontSize: 9, fontWeight: "900", paddingHorizontal: 5, paddingVertical: 2, borderRadius: 4, overflow: "hidden" },
  valueLegend: { marginTop: 10 },
  valueLegendText: { color: C.muted, fontSize: 10, lineHeight: 15 },
  methodText: { color: C.muted, fontSize: 9, marginTop: 2 },
  card: { backgroundColor: C.card, borderRadius: 16, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: C.border },
  cardTitle: { color: C.text, fontSize: 15, fontWeight: "700", marginBottom: 14 },
  statsGrid: { marginTop: 12, borderTopWidth: 1, borderTopColor: C.border, paddingTop: 12 },
  statRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 6 },
  statValue: { color: C.primary, fontSize: 14, fontWeight: "700", width: 50, textAlign: "center" },
  statLabel: { color: C.muted, fontSize: 12, flex: 1, textAlign: "center" },
  h2hRow: { flexDirection: "row", justifyContent: "space-around" },
  h2hItem: { alignItems: "center" },
  h2hVal: { fontSize: 28, fontWeight: "900" },
  h2hLabel: { color: C.muted, fontSize: 11, marginTop: 4, textAlign: "center" },
  analysisCard: { borderColor: C.primary + "44" },
  analysisHeader: { flexDirection: "row", alignItems: "center", marginBottom: 12 },
  analysisIcon: { fontSize: 18, marginRight: 8 },
  analysisText: { color: C.text, fontSize: 14, lineHeight: 22 },
});
