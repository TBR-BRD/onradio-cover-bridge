package de.tbrbd.onradiotv.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.focusable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import de.tbrbd.onradiotv.model.Station
import de.tbrbd.onradiotv.model.WeatherState
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.delay

private val BgColor = Color(0xFF080B14)
private val PanelColor = Color(0xFF10152E)
private val AccentColor = Color(0xFF7AB6FF)
private val FocusColor = Color(0xFFFFD166)
private val MutedColor = Color(0xFFB3BDD6)
private val TextColor = Color(0xFFF6F8FF)
private val ScrimColor = Color(0xCC05070D)

private val ENTER_KEYS = setOf(Key.Enter, Key.NumPadEnter, Key.DirectionCenter)

@Composable
fun TvScreen(
    state: TvUiState,
    onSelectStation: (String) -> Unit,
) {
    var isPickerOpen by remember { mutableStateOf(false) }

    Box(modifier = Modifier.fillMaxSize().background(BgColor)) {
        Row(
            modifier = Modifier
                .fillMaxSize()
                .padding(48.dp),
            horizontalArrangement = Arrangement.spacedBy(48.dp),
        ) {
            CoverColumn(coverUrl = state.coverUrl, modifier = Modifier.weight(0.42f).fillMaxHeight())
            SideColumn(
                state = state,
                onOpenPicker = { isPickerOpen = true },
                modifier = Modifier.weight(0.58f).fillMaxHeight(),
            )
        }

        if (isPickerOpen) {
            StationPickerOverlay(
                stations = state.stations,
                currentStationId = state.currentStationId,
                onSelect = { id ->
                    onSelectStation(id)
                    isPickerOpen = false
                },
                onDismiss = { isPickerOpen = false },
            )
        }
    }
}

@Composable
private fun CoverColumn(coverUrl: String?, modifier: Modifier = Modifier) {
    Box(modifier = modifier, contentAlignment = Alignment.Center) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(1f)
                .clip(RoundedCornerShape(24.dp)),
            color = PanelColor,
        ) {
            AsyncImage(
                model = coverUrl,
                contentDescription = "Albumcover",
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize(),
            )
        }
    }
}

@Composable
private fun SideColumn(
    state: TvUiState,
    onOpenPicker: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val currentStation = state.stations.find { it.id == state.currentStationId }

    Column(modifier = modifier, verticalArrangement = Arrangement.SpaceBetween) {
        Column {
            Header(stationName = currentStation?.name ?: "OnRadio TV")

            Text(
                text = state.nowPlaying?.title ?: "Noch kein Titel",
                color = TextColor,
                fontSize = 40.sp,
                fontWeight = FontWeight.Bold,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = 24.dp),
            )
            Text(
                text = state.nowPlaying?.artist ?: "Bitte einen Sender auswählen.",
                color = MutedColor,
                fontSize = 22.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = 8.dp),
            )

            WeatherPanel(weather = state.weather, modifier = Modifier.padding(top = 32.dp))
        }

        StationSelectorButton(
            stationName = currentStation?.name ?: "Sender wählen",
            onOpen = onOpenPicker,
        )
    }
}

@Composable
private fun Header(stationName: String) {
    var now by remember { mutableStateOf(Date()) }
    LaunchedEffect(Unit) {
        while (true) {
            now = Date()
            delay(1000)
        }
    }
    val timeFormat = remember { SimpleDateFormat("HH:mm", Locale.GERMANY) }
    val dateFormat = remember { SimpleDateFormat("EEEE, dd.MM.", Locale.GERMANY) }

    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.Top,
    ) {
        Text(text = stationName, color = AccentColor, fontSize = 24.sp, fontWeight = FontWeight.SemiBold)
        Column(horizontalAlignment = Alignment.End) {
            Text(text = timeFormat.format(now), color = TextColor, fontSize = 40.sp, fontWeight = FontWeight.Bold)
            Text(text = dateFormat.format(now), color = MutedColor, fontSize = 16.sp)
        }
    }
}

@Composable
private fun WeatherPanel(weather: WeatherState?, modifier: Modifier = Modifier) {
    if (weather == null) return
    Surface(
        modifier = modifier.fillMaxWidth(),
        color = PanelColor,
        shape = RoundedCornerShape(16.dp),
    ) {
        Column(modifier = Modifier.padding(20.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = weather.temperatureC?.let { "${it.toInt()}°" } ?: "--°",
                    color = TextColor,
                    fontSize = 34.sp,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = "  ${weather.condition}",
                    color = MutedColor,
                    fontSize = 18.sp,
                    modifier = Modifier.padding(start = 8.dp),
                )
            }
            Row(
                modifier = Modifier.padding(top = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                weather.days.take(3).forEach { day ->
                    Column {
                        Text(text = day.label, color = MutedColor, fontSize = 14.sp)
                        val max = day.tempMaxC?.let { "${it.toInt()}°" } ?: "--°"
                        val min = day.tempMinC?.let { "${it.toInt()}°" } ?: "--°"
                        Text(text = "$max / $min", color = TextColor, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }
    }
}

/** The always-visible trigger on the main screen; opens the full picker. */
@Composable
private fun StationSelectorButton(stationName: String, onOpen: () -> Unit) {
    val interactionSource = remember { MutableInteractionSource() }
    val isFocused by interactionSource.collectIsFocusedAsState()
    val focusRequester = remember { FocusRequester() }

    val borderColor = if (isFocused) FocusColor else Color(0x1AFFFFFF)
    val backgroundColor = if (isFocused) Color(0x29FFD166) else PanelColor

    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .focusRequester(focusRequester)
            .focusable(interactionSource = interactionSource)
            .onKeyEvent { event ->
                if (event.type == KeyEventType.KeyDown && event.key in ENTER_KEYS) {
                    onOpen()
                    true
                } else {
                    false
                }
            },
        color = backgroundColor,
        shape = RoundedCornerShape(12.dp),
        border = BorderStroke(2.dp, borderColor),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp, vertical = 16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text("Sender", color = MutedColor, fontSize = 13.sp)
                Text(stationName, color = TextColor, fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
            }
            Text("OK ▾", color = MutedColor, fontSize = 16.sp)
        }
    }

    // The main screen has exactly this one focusable widget, so it should
    // already carry the D-pad focus as soon as the screen appears.
    LaunchedEffect(Unit) {
        try {
            focusRequester.requestFocus()
        } catch (_: IllegalStateException) {
            // Not laid out yet on this frame - harmless, the button is still
            // reachable, it just won't have focus by default this one time.
        }
    }
}

/**
 * Two-pane picker: station "families" (ON Radio, RADIO BOB!, ENERGY, ...) on
 * the left, the stations within the highlighted family on the right. This
 * replaced a single flat list of all 253 stations, which was unusable with a
 * D-pad (up to 253 presses to reach the last one) - the biggest single
 * family now tops out at 67 (RADIO BOB!).
 */
@Composable
private fun StationPickerOverlay(
    stations: List<Station>,
    currentStationId: String?,
    onSelect: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    BackHandler(onBack = onDismiss)

    val focusManager = LocalFocusManager.current
    val groups = remember(stations) {
        stations.groupBy { it.group }.map { (name, list) -> name to list }
    }
    val currentGroup = remember(stations, currentStationId) {
        stations.find { it.id == currentStationId }?.group ?: groups.firstOrNull()?.first ?: ""
    }
    var selectedGroup by remember(stations) { mutableStateOf(currentGroup) }
    val groupFocusRequesters = remember(groups) { groups.associate { it.first to FocusRequester() } }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(ScrimColor)
            .onKeyEvent { event ->
                if (event.type != KeyEventType.KeyDown) return@onKeyEvent false
                when (event.key) {
                    Key.DirectionUp -> {
                        focusManager.moveFocus(FocusDirection.Up); true
                    }
                    Key.DirectionDown -> {
                        focusManager.moveFocus(FocusDirection.Down); true
                    }
                    Key.DirectionLeft -> {
                        focusManager.moveFocus(FocusDirection.Left); true
                    }
                    Key.DirectionRight -> {
                        focusManager.moveFocus(FocusDirection.Right); true
                    }
                    else -> false
                }
            },
        contentAlignment = Alignment.CenterEnd,
    ) {
        Surface(
            modifier = Modifier
                .fillMaxHeight(0.86f)
                .width(880.dp)
                .padding(end = 24.dp),
            color = PanelColor,
            shape = RoundedCornerShape(20.dp),
        ) {
            Column(modifier = Modifier.padding(24.dp)) {
                Text("Sender wählen", color = TextColor, fontSize = 24.sp, fontWeight = FontWeight.Bold)
                Text(
                    "◀ ▶ Kategorie/Liste · ▲ ▼ navigieren · OK wählt · Zurück schließt",
                    color = MutedColor,
                    fontSize = 14.sp,
                    modifier = Modifier.padding(top = 4.dp, bottom = 16.dp),
                )

                Row(modifier = Modifier.weight(1f).fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(20.dp)) {
                    GroupList(
                        groups = groups,
                        selectedGroup = selectedGroup,
                        onGroupFocused = { selectedGroup = it },
                        focusRequesters = groupFocusRequesters,
                        modifier = Modifier.weight(0.4f).fillMaxHeight(),
                    )
                    StationList(
                        stations = groups.find { it.first == selectedGroup }?.second ?: emptyList(),
                        currentStationId = currentStationId,
                        onSelect = onSelect,
                        modifier = Modifier.weight(0.6f).fillMaxHeight(),
                    )
                }
            }
        }
    }

    LaunchedEffect(groups) {
        try {
            groupFocusRequesters[selectedGroup]?.requestFocus()
        } catch (_: IllegalStateException) {
            // Not laid out yet this frame - list stays usable, just without
            // an initial focus target this one time.
        }
    }
}

@Composable
private fun GroupList(
    groups: List<Pair<String, List<Station>>>,
    selectedGroup: String?,
    onGroupFocused: (String) -> Unit,
    focusRequesters: Map<String, FocusRequester>,
    modifier: Modifier = Modifier,
) {
    LazyColumn(modifier = modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        items(groups, key = { it.first }) { (groupName, groupStations) ->
            val interactionSource = remember { MutableInteractionSource() }
            val isFocused by interactionSource.collectIsFocusedAsState()
            val isSelected = groupName == selectedGroup

            val backgroundColor = when {
                isFocused -> Color(0x29FFD166)
                isSelected -> Color(0x2E4E95FF)
                else -> Color.Transparent
            }
            val borderColor = when {
                isFocused -> FocusColor
                isSelected -> AccentColor
                else -> Color.Transparent
            }

            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .focusRequester(focusRequesters.getValue(groupName))
                    .focusable(interactionSource = interactionSource)
                    .onFocusChanged { if (it.isFocused) onGroupFocused(groupName) },
                color = backgroundColor,
                shape = RoundedCornerShape(10.dp),
                border = BorderStroke(2.dp, borderColor),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Text(groupName, color = TextColor, fontSize = 16.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text("${groupStations.size}", color = MutedColor, fontSize = 14.sp)
                }
            }
        }
    }
}

@Composable
private fun StationList(
    stations: List<Station>,
    currentStationId: String?,
    onSelect: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    key(stations.firstOrNull()?.group) {
        val listState = rememberLazyListState()
        LazyColumn(
            state = listState,
            modifier = modifier,
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(stations, key = { it.id }) { station ->
                StationListItem(
                    station = station,
                    isCurrent = station.id == currentStationId,
                    onSelect = { onSelect(station.id) },
                )
            }
        }
    }
}

@Composable
private fun StationListItem(
    station: Station,
    isCurrent: Boolean,
    onSelect: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val interactionSource = remember { MutableInteractionSource() }
    val isFocused by interactionSource.collectIsFocusedAsState()

    val backgroundColor = when {
        isFocused -> Color(0x29FFD166)
        isCurrent -> Color(0x2E4E95FF)
        else -> Color.Transparent
    }
    val borderColor = when {
        isFocused -> FocusColor
        isCurrent -> AccentColor
        else -> Color.Transparent
    }

    Surface(
        modifier = modifier
            .fillMaxWidth()
            .focusable(interactionSource = interactionSource)
            .onKeyEvent { event ->
                if (event.type == KeyEventType.KeyDown && event.key in ENTER_KEYS) {
                    onSelect()
                    true
                } else {
                    false
                }
            },
        color = backgroundColor,
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(2.dp, borderColor),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 14.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = station.name,
                color = TextColor,
                fontSize = 18.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            if (isCurrent) {
                Text("▶", color = AccentColor, fontSize = 16.sp)
            }
        }
    }
}
