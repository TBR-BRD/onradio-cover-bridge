package de.tbrbd.onradiotv.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.focusable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.Key
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

@Composable
fun TvScreen(
    state: TvUiState,
    onSelectStation: (String) -> Unit,
    onFocusStation: (String) -> Unit,
) {
    val focusManager = LocalFocusManager.current

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(BgColor)
            .onKeyEvent { event ->
                if (event.type != androidx.compose.ui.input.key.KeyEventType.KeyDown) return@onKeyEvent false
                when (event.key) {
                    Key.DirectionLeft -> {
                        focusManager.moveFocus(androidx.compose.ui.focus.FocusDirection.Left)
                        true
                    }
                    Key.DirectionRight -> {
                        focusManager.moveFocus(androidx.compose.ui.focus.FocusDirection.Right)
                        true
                    }
                    Key.Enter, Key.NumPadEnter, Key.DirectionCenter -> {
                        state.focusedStationId?.let(onSelectStation)
                        true
                    }
                    else -> false
                }
            },
    ) {
        Row(
            modifier = Modifier
                .fillMaxSize()
                .padding(48.dp),
            horizontalArrangement = Arrangement.spacedBy(48.dp),
        ) {
            CoverColumn(coverUrl = state.coverUrl, modifier = Modifier.weight(0.42f).fillMaxHeight())
            SideColumn(state = state, onFocusStation = onFocusStation, onSelectStation = onSelectStation, modifier = Modifier.weight(0.58f).fillMaxHeight())
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
    onFocusStation: (String) -> Unit,
    onSelectStation: (String) -> Unit,
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

        StationRow(
            stations = state.stations,
            currentStationId = state.currentStationId,
            focusedStationId = state.focusedStationId,
            onFocusStation = onFocusStation,
            onSelectStation = onSelectStation,
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

@Composable
private fun StationRow(
    stations: List<Station>,
    currentStationId: String?,
    focusedStationId: String?,
    onFocusStation: (String) -> Unit,
    onSelectStation: (String) -> Unit,
) {
    val firstItemFocusRequester = remember { FocusRequester() }

    Column {
        Text(
            text = "Sender  (◀ ▶ wählen · OK schaltet um)",
            color = MutedColor,
            fontSize = 14.sp,
            modifier = Modifier.padding(bottom = 12.dp),
        )
        LazyRow(
            horizontalArrangement = Arrangement.spacedBy(16.dp),
            contentPadding = PaddingValues(vertical = 8.dp),
        ) {
            items(stations, key = { it.id }) { station ->
                val isFirst = station.id == stations.firstOrNull()?.id
                StationChip(
                    station = station,
                    isCurrent = station.id == currentStationId,
                    onFocused = { onFocusStation(station.id) },
                    onSelect = { onSelectStation(station.id) },
                    modifier = if (isFirst) Modifier.focusRequester(firstItemFocusRequester) else Modifier,
                )
            }
        }
    }

    LaunchedEffect(stations) {
        if (stations.isNotEmpty()) {
            firstItemFocusRequester.requestFocus()
        }
    }
}

@Composable
private fun StationChip(
    station: Station,
    isCurrent: Boolean,
    onFocused: () -> Unit,
    onSelect: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val interactionSource = remember { MutableInteractionSource() }
    val isFocused by interactionSource.collectIsFocusedAsState()

    val borderColor = when {
        isFocused -> FocusColor
        isCurrent -> AccentColor
        else -> Color(0x1AFFFFFF)
    }
    val backgroundColor = when {
        isFocused -> Color(0x29FFD166)
        isCurrent -> Color(0x2E4E95FF)
        else -> PanelColor
    }

    Surface(
        modifier = modifier
            .width(220.dp)
            .onFocusChanged { if (it.isFocused) onFocused() }
            .focusable(interactionSource = interactionSource)
            .onKeyEvent { event ->
                if (event.type == androidx.compose.ui.input.key.KeyEventType.KeyDown &&
                    (event.key == Key.Enter || event.key == Key.DirectionCenter || event.key == Key.NumPadEnter)
                ) {
                    onSelect()
                    true
                } else {
                    false
                }
            },
        color = backgroundColor,
        shape = RoundedCornerShape(12.dp),
        border = androidx.compose.foundation.BorderStroke(2.dp, borderColor),
    ) {
        Text(
            text = station.name,
            color = TextColor,
            fontSize = 18.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.padding(horizontal = 20.dp, vertical = 16.dp),
        )
    }
}
