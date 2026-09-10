import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  SafeAreaView,
  Image,
} from "react-native";
import { useRouter } from "expo-router";
import { getCompetitions, describeError, Competition } from "../../services/api";

const C = {
  bg: "#0a1628",
  card: "#1a2744",
  primary: "#00c853",
  text: "#ffffff",
  muted: "#8892a4",
  border: "#2d3748",
};

export default function LeaguesScreen() {
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    getCompetitions()
      .then((res) => {
        setCompetitions(res.data.competitions || []);
        setError(null);
      })
      // Avant : .catch(() => setCompetitions([])) -- toute panne se traduisait
      // par une liste vide, sans dire pourquoi.
      .catch((e) => setError(describeError(e)))
      .finally(() => setLoading(false));
  }, []);

  const renderItem = ({ item }: { item: Competition }) => (
    <TouchableOpacity
      style={s.card}
      activeOpacity={0.8}
      onPress={() =>
        // Renvoyait vers "/(tabs)/index", qui ne lit aucun parametre :
        // taper un championnat n'affichait donc jamais rien.
        router.push({
          pathname: "/league/[code]",
          params: { code: item.code, name: item.name },
        })
      }
      disabled={!item.code}
    >
      {item.emblem ? (
        <Image source={{ uri: item.emblem }} style={s.emblem} />
      ) : (
        <View style={s.emblemPlaceholder}>
          <Text style={{ fontSize: 20 }}>🏆</Text>
        </View>
      )}
      <View style={s.info}>
        <Text style={s.name} numberOfLines={1}>{item.name}</Text>
        <Text style={s.area}>{item.area} · {item.type === "LEAGUE" ? "Championnat" : "Coupe"}</Text>
      </View>
      <Text style={s.arrow}>›</Text>
    </TouchableOpacity>
  );

  return (
    <SafeAreaView style={s.container}>
      <View style={s.header}>
        <Text style={s.headerTitle}>🏆 Ligues & Compétitions</Text>
        <Text style={s.headerSub}>Toutes les compétitions disponibles</Text>
      </View>

      {loading ? (
        <View style={s.center}>
          <ActivityIndicator size="large" color={C.primary} />
        </View>
      ) : error ? (
        <View style={s.center}>
          <Text style={s.errorText}>{error}</Text>
        </View>
      ) : (
        <FlatList
          data={competitions}
          keyExtractor={(item) => item.id.toString()}
          renderItem={renderItem}
          contentContainerStyle={s.list}
        />
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: C.bg },
  header: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 8 },
  headerTitle: { color: C.text, fontSize: 22, fontWeight: "800" },
  headerSub: { color: C.muted, fontSize: 12, marginTop: 2 },
  list: { paddingHorizontal: 16, paddingBottom: 20 },
  card: { flexDirection: "row", alignItems: "center", backgroundColor: C.card, borderRadius: 14, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: C.border },
  emblem: { width: 40, height: 40, borderRadius: 20 },
  emblemPlaceholder: { width: 40, height: 40, borderRadius: 20, backgroundColor: C.border, justifyContent: "center", alignItems: "center" },
  info: { flex: 1, marginLeft: 14 },
  name: { color: C.text, fontSize: 14, fontWeight: "700" },
  area: { color: C.muted, fontSize: 12, marginTop: 3 },
  arrow: { color: C.primary, fontSize: 24, fontWeight: "300" },
  center: { flex: 1, justifyContent: "center", alignItems: "center", padding: 24 },
  errorText: { color: "#ff5252", fontSize: 14, textAlign: "center" },
});
