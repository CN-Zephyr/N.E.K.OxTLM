import {
  Page,
  Card,
  Stack,
  Text,
  StatusBadge,
  KeyValue,
  Select,
  Field,
  Input,
  Alert,
  Divider,
  EmptyState,
  ActionButton,
  RefreshButton,
  useEffect,
  useState,
} from "@neko/plugin-ui"
import type { HostedAction, PluginSurfaceProps } from "@neko/plugin-ui"

type MaidInfo = {
  id: string
  name: string
  health: number
  max_health: number
  is_sitting: boolean
  is_following: boolean
  owner: string
}

type State = {
  connected: boolean
  ws_url: string
  maids: MaidInfo[]
  assigned_maid_id: string
  assigned_maid_name: string
  command_execution_enabled: boolean
  companion_mode: string
  companion_settings: Record<string, number>
  last_diagnostic?: DiagnosticResult | null
}

type DiagnosticCheck = {
  status: string
  title: string
  detail: string
  suggestion?: string
}

type DiagnosticResult = {
  status: string
  summary: string
  checks: DiagnosticCheck[]
}

export default function Panel(props: PluginSurfaceProps<State>) {
  const { t, state, actions, useLocalState } = props

  const connected = state?.connected ?? false
  const maids = state?.maids ?? []
  const assignedId = state?.assigned_maid_id ?? ""
  const assignedName = state?.assigned_maid_name ?? ""
  const commandExecutionEnabled = state?.command_execution_enabled ?? false
  const companionMode = state?.companion_mode ?? "custom"
  const companionSettings = state?.companion_settings ?? {}
  const diagnostic = state?.last_diagnostic ?? null

  const [selectedMaidId, setSelectedMaidId] = useLocalState<string>("selectedMaidId", "")
  const settingText = (key: string) => String(companionSettings[key] ?? "")
  const [selectedCompanionMode, setSelectedCompanionMode] = useState<string>(companionMode)
  const [customAwarenessInterval, setCustomAwarenessInterval] = useState<string>(settingText("awareness_interval"))
  const [customActivityCooldown, setCustomActivityCooldown] = useState<string>(settingText("playmate_activity_cooldown"))
  const [customQuietStableSeconds, setCustomQuietStableSeconds] = useState<string>(settingText("playmate_quiet_stable_seconds"))
  const [customQuietCooldown, setCustomQuietCooldown] = useState<string>(settingText("playmate_quiet_cooldown"))
  const [customAggregateWindow, setCustomAggregateWindow] = useState<string>(settingText("playmate_aggregate_window"))
  const [customThrottleWindow, setCustomThrottleWindow] = useState<string>(settingText("playmate_throttle_window"))
  const [customThrottleLimit, setCustomThrottleLimit] = useState<string>(settingText("playmate_throttle_limit"))
  const [customSuggestionCooldown, setCustomSuggestionCooldown] = useState<string>(settingText("playmate_suggestion_cooldown"))

  useEffect(() => {
    setSelectedCompanionMode(companionMode)
    setCustomAwarenessInterval(settingText("awareness_interval"))
    setCustomActivityCooldown(settingText("playmate_activity_cooldown"))
    setCustomQuietStableSeconds(settingText("playmate_quiet_stable_seconds"))
    setCustomQuietCooldown(settingText("playmate_quiet_cooldown"))
    setCustomAggregateWindow(settingText("playmate_aggregate_window"))
    setCustomThrottleWindow(settingText("playmate_throttle_window"))
    setCustomThrottleLimit(settingText("playmate_throttle_limit"))
    setCustomSuggestionCooldown(settingText("playmate_suggestion_cooldown"))
  }, [
    companionMode,
    companionSettings.awareness_interval,
    companionSettings.playmate_activity_cooldown,
    companionSettings.playmate_quiet_stable_seconds,
    companionSettings.playmate_quiet_cooldown,
    companionSettings.playmate_aggregate_window,
    companionSettings.playmate_throttle_window,
    companionSettings.playmate_throttle_limit,
    companionSettings.playmate_suggestion_cooldown,
  ])

  const assignAction = actions.find((a) => a.id === "assign_maid") as HostedAction | undefined
  const refreshAction = actions.find((a) => a.id === "refresh_maid_status") as HostedAction | undefined
  const diagnoseAction = actions.find((a) => a.id === "diagnose_bridge") as HostedAction | undefined
  const setCompanionModeAction = actions.find((a) => a.id === "set_companion_mode") as HostedAction | undefined

  const companionModeOptions = ["quiet", "standard", "active", "custom"].map((mode) => ({
    value: mode,
    label: t(`companionMode.${mode}`),
  }))

  const effectiveCompanionMode = selectedCompanionMode || companionMode
  const customValue = (key: string, draft: string) => draft || String(companionSettings[key] ?? "")
  const customCompanionValues = {
    awareness_interval: customValue("awareness_interval", customAwarenessInterval),
    playmate_activity_cooldown: customValue("playmate_activity_cooldown", customActivityCooldown),
    playmate_quiet_stable_seconds: customValue("playmate_quiet_stable_seconds", customQuietStableSeconds),
    playmate_quiet_cooldown: customValue("playmate_quiet_cooldown", customQuietCooldown),
    playmate_aggregate_window: customValue("playmate_aggregate_window", customAggregateWindow),
    playmate_throttle_window: customValue("playmate_throttle_window", customThrottleWindow),
    playmate_throttle_limit: customValue("playmate_throttle_limit", customThrottleLimit),
    playmate_suggestion_cooldown: customValue("playmate_suggestion_cooldown", customSuggestionCooldown),
  }

  const maidOptions = [
    { value: "", label: t("maid.selectPlaceholder") },
    ...maids.map((m) => ({
      value: m.id,
      label: `${m.name} (${m.id.substring(0, 8)}...)`,
    })),
  ]

  const assignedMaid = maids.find((m) => m.id === assignedId)
  const selectedMaid = maids.find((m) => m.id === selectedMaidId)

  if (state == null) {
    return (
      <Page title={t("panel.title")} subtitle={t("panel.subtitle")}>
        <Card title={t("connection.title")}>
          <Stack>
            <StatusBadge tone="error">{t("connection.pluginNotEnabled")}</StatusBadge>
            <Text>{t("connection.pluginNotEnabledHint")}</Text>
            <RefreshButton />
          </Stack>
        </Card>
      </Page>
    )
  }

  return (
    <Page title={t("panel.title")} subtitle={t("panel.subtitle")}>
      <Card title={t("connection.title")}>
        <Stack>
          <StatusBadge tone={connected ? "success" : "error"}>
            {connected ? t("connection.connected") : t("connection.disconnected")}
          </StatusBadge>
          <KeyValue
            items={[
              { key: t("connection.wsUrl"), value: state?.ws_url ?? "-" },
              { key: t("connection.companionMode"), value: t(`companionMode.${companionMode}`) },
            ]}
          />
          <Stack direction="horizontal">
            <RefreshButton />
            {refreshAction && (
              <ActionButton action={refreshAction}>{t("actions.refresh")}</ActionButton>
            )}
            {diagnoseAction && (
              <ActionButton action={diagnoseAction}>{t("actions.diagnose")}</ActionButton>
            )}
          </Stack>
        </Stack>
      </Card>

      <Card title={t("companion.title")}>
        <Stack>
          <Text>{t("companion.description")}</Text>
          <Select
            options={companionModeOptions}
            value={effectiveCompanionMode}
            onChange={setSelectedCompanionMode}
          />
          <Text>{t(`companion.modeSummary.${effectiveCompanionMode}`)}</Text>
          {effectiveCompanionMode === "custom" && (
            <Stack>
              <Alert tone="info">{t("companion.customHint")}</Alert>
              <Field label={t("companion.fields.awarenessInterval")} help={t("companion.fields.awarenessIntervalHelp")}>
                <Input value={customCompanionValues.awareness_interval} onChange={setCustomAwarenessInterval} />
              </Field>
              <Field label={t("companion.fields.activityCooldown")} help={t("companion.fields.activityCooldownHelp")}>
                <Input value={customCompanionValues.playmate_activity_cooldown} onChange={setCustomActivityCooldown} />
              </Field>
              <Field label={t("companion.fields.quietStableSeconds")} help={t("companion.fields.quietStableSecondsHelp")}>
                <Input value={customCompanionValues.playmate_quiet_stable_seconds} onChange={setCustomQuietStableSeconds} />
              </Field>
              <Field label={t("companion.fields.quietCooldown")} help={t("companion.fields.quietCooldownHelp")}>
                <Input value={customCompanionValues.playmate_quiet_cooldown} onChange={setCustomQuietCooldown} />
              </Field>
              <Field label={t("companion.fields.aggregateWindow")} help={t("companion.fields.aggregateWindowHelp")}>
                <Input value={customCompanionValues.playmate_aggregate_window} onChange={setCustomAggregateWindow} />
              </Field>
              <Field label={t("companion.fields.throttleWindow")} help={t("companion.fields.throttleWindowHelp")}>
                <Input value={customCompanionValues.playmate_throttle_window} onChange={setCustomThrottleWindow} />
              </Field>
              <Field label={t("companion.fields.throttleLimit")} help={t("companion.fields.throttleLimitHelp")}>
                <Input value={customCompanionValues.playmate_throttle_limit} onChange={setCustomThrottleLimit} />
              </Field>
              <Field label={t("companion.fields.suggestionCooldown")} help={t("companion.fields.suggestionCooldownHelp")}>
                <Input value={customCompanionValues.playmate_suggestion_cooldown} onChange={setCustomSuggestionCooldown} />
              </Field>
            </Stack>
          )}
          {setCompanionModeAction && (
            <ActionButton
              action={setCompanionModeAction}
              values={{
                mode: effectiveCompanionMode,
                ...(effectiveCompanionMode === "custom" ? customCompanionValues : {}),
              }}
            >
              {t("actions.setCompanionMode")}
            </ActionButton>
          )}
        </Stack>
      </Card>

      {diagnostic && (
        <Card title={t("diagnostic.title")}>
          <Stack>
            <Alert tone={diagnostic.status === "ok" ? "success" : diagnostic.status === "error" ? "error" : "warning"}>
              {diagnostic.summary}
            </Alert>
            <KeyValue
              items={diagnostic.checks.map((check) => ({
                key: `${t(`diagnostic.status.${check.status}`)} · ${check.title}`,
                value: check.suggestion ? `${check.detail} ${check.suggestion}` : check.detail,
              }))}
            />
          </Stack>
        </Card>
      )}

      <Card title={t("command.title")}>
        <Stack>
          <Alert tone={commandExecutionEnabled ? "success" : "warning"}>
            {commandExecutionEnabled ? t("command.enabled") : t("command.disabled")}
          </Alert>
          <Text>{t("command.description")}</Text>
        </Stack>
      </Card>

      <Card title={t("maid.title")}>
        <Stack>
          {assignedId && assignedName ? (
            <Alert tone="success">{t("maid.assigned", { name: assignedName })}</Alert>
          ) : (
            <Alert tone="warning">{t("maid.notAssigned")}</Alert>
          )}

          {assignedMaid && (
            <KeyValue
              items={[
                { key: t("maid.name"), value: assignedMaid.name },
                { key: t("maid.health"), value: `${assignedMaid.health}/${assignedMaid.max_health}` },
                { key: t("maid.sitting"), value: assignedMaid.is_sitting ? t("yes") : t("no") },
                { key: t("maid.following"), value: assignedMaid.is_following ? t("yes") : t("no") },
                { key: t("maid.owner"), value: assignedMaid.owner },
              ]}
            />
          )}

          <Divider />

          {maids.length > 0 ? (
            <Stack>
              <Text>{t("maid.selectHint")}</Text>
              <Select
                options={maidOptions}
                value={selectedMaidId}
                onChange={setSelectedMaidId}
              />
              {assignAction && selectedMaidId && (
                <ActionButton
                  action={assignAction}
                  values={{ maid_id: selectedMaidId, maid_name: selectedMaid?.name ?? "" }}
                >
                  {t("actions.assignMaid")}
                </ActionButton>
              )}
            </Stack>
          ) : connected ? (
            <EmptyState title={t("maid.noMaids")} description={t("maid.noMaidsHint")} />
          ) : (
            <EmptyState title={t("maid.connectFirst")} description={t("maid.connectFirstHint")} />
          )}
        </Stack>
      </Card>
    </Page>
  )
}
