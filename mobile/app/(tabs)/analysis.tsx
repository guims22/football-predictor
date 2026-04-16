import React, { useState, useRef } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  SafeAreaView,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { api } from "../../services/api";

const C = {
  bg: "#0a1628",
  card: "#1a2744",
  primary: "#00c853",
  accent: "#1565c0",
  text: "#ffffff",
  muted: "#8892a4",
  border: "#2d3748",
  userMsg: "#1565c0",
  aiMsg: "#1a2744",
};

interface Message {
  role: "user" | "assistant";
  text: string;
}

const SUGGESTIONS = [
  "Qui va gagner PSG vs Real Madrid ?",
  "Quelle est la meilleure équipe de Premier League cette saison ?",
  "Analyse la forme de Manchester City",
  "Top 3 des équipes en forme en Ligue 1",
];

export default function AnalysisScreen() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      text: "Bonjour ! Je suis votre assistant football alimenté par Claude AI. Posez-moi n'importe quelle question sur le football : analyses d'équipes, prédictions, statistiques...",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<ScrollView>(null);

  const sendMessage = async (text: string) => {
    const question = text.trim();
    if (!question || loading) return;

    const newMessages: Message[] = [
      ...messages,
      { role: "user", text: question },
    ];
    setMessages(newMessages);
    setInput("");
    setLoading(true);

    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);

    try {
      const res = await api.post<{ response: string }>("/analysis/chat", {
        question,
        history: newMessages.slice(-6).map((m) => ({
          role: m.role,
          content: m.text,
        })),
      });
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: res.data.response },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: "Désolé, une erreur est survenue. Vérifiez votre connexion.",
        },
      ]);
    } finally {
      setLoading(false);
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);
    }
  };

  return (
    <SafeAreaView style={s.container}>
      <View style={s.header}>
        <Text style={s.headerTitle}>✨ Analyse IA</Text>
        <Text style={s.headerSub}>Discutez avec Claude AI sur le football</Text>
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={80}
      >
        <ScrollView
          ref={scrollRef}
          style={s.chat}
          contentContainerStyle={s.chatContent}
          onContentSizeChange={() => scrollRef.current?.scrollToEnd()}
        >
          {messages.map((msg, i) => (
            <View
              key={i}
              style={[
                s.bubble,
                msg.role === "user" ? s.userBubble : s.aiBubble,
              ]}
            >
              {msg.role === "assistant" && (
                <Text style={s.aiLabel}>✨ Claude AI</Text>
              )}
              <Text style={s.bubbleText}>{msg.text}</Text>
            </View>
          ))}
          {loading && (
            <View style={s.aiBubble}>
              <Text style={s.aiLabel}>✨ Claude AI</Text>
              <ActivityIndicator size="small" color={C.primary} />
            </View>
          )}

          {messages.length === 1 && (
            <View style={s.suggestions}>
              <Text style={s.suggestTitle}>Suggestions :</Text>
              {SUGGESTIONS.map((s_) => (
                <TouchableOpacity
                  key={s_}
                  style={s.suggestBtn}
                  onPress={() => sendMessage(s_)}
                >
                  <Text style={s.suggestText}>{s_}</Text>
                </TouchableOpacity>
              ))}
            </View>
          )}
        </ScrollView>

        <View style={s.inputRow}>
          <TextInput
            style={s.input}
            placeholder="Posez votre question football..."
            placeholderTextColor={C.muted}
            value={input}
            onChangeText={setInput}
            onSubmitEditing={() => sendMessage(input)}
            returnKeyType="send"
            multiline
          />
          <TouchableOpacity
            style={[s.sendBtn, (!input.trim() || loading) && s.sendBtnDisabled]}
            onPress={() => sendMessage(input)}
            disabled={!input.trim() || loading}
          >
            <Text style={s.sendIcon}>➤</Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: C.bg },
  header: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 8 },
  headerTitle: { color: C.text, fontSize: 22, fontWeight: "800" },
  headerSub: { color: C.muted, fontSize: 12, marginTop: 2 },
  chat: { flex: 1 },
  chatContent: { padding: 16, gap: 12 },
  bubble: { borderRadius: 16, padding: 14, maxWidth: "88%" },
  userBubble: { backgroundColor: C.userMsg, alignSelf: "flex-end" },
  aiBubble: { backgroundColor: C.aiMsg, alignSelf: "flex-start", borderWidth: 1, borderColor: C.border },
  aiLabel: { color: C.primary, fontSize: 11, fontWeight: "700", marginBottom: 6 },
  bubbleText: { color: C.text, fontSize: 14, lineHeight: 21 },
  inputRow: { flexDirection: "row", alignItems: "flex-end", padding: 12, backgroundColor: C.card, borderTopWidth: 1, borderTopColor: C.border, gap: 10 },
  input: { flex: 1, color: C.text, backgroundColor: C.bg, borderRadius: 20, paddingHorizontal: 16, paddingVertical: 10, fontSize: 14, maxHeight: 100, borderWidth: 1, borderColor: C.border },
  sendBtn: { width: 44, height: 44, backgroundColor: C.primary, borderRadius: 22, justifyContent: "center", alignItems: "center" },
  sendBtnDisabled: { opacity: 0.4 },
  sendIcon: { color: "#000", fontSize: 16, fontWeight: "700" },
  suggestions: { marginTop: 8 },
  suggestTitle: { color: C.muted, fontSize: 12, marginBottom: 8 },
  suggestBtn: { backgroundColor: C.card, borderRadius: 10, padding: 12, marginBottom: 8, borderWidth: 1, borderColor: C.border },
  suggestText: { color: C.text, fontSize: 13 },
});
