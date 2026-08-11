<!-- 折线图，支持多组数据，支持阶梯式动画效果 -->
<template>
  <div
    ref="chartRef"
    class="relative w-[calc(100%+10px)]"
    :style="{ height: props.height }"
    v-loading="props.loading"
  >
  </div>
</template>

<script setup lang="ts">
  import { echarts, graphic, type EChartsOption } from '@/plugins/echarts'
  import { getCssVar, hexToRgba } from '@/utils/ui'
  import { useChartOps, useChartComponent } from '@/hooks/core/useChart'
  import type { LineChartProps, LineDataItem } from '@/types/component/chart'

  defineOptions({ name: 'ArtLineChart' })

  const props = withDefaults(defineProps<LineChartProps>(), {
    // 基础配置
    height: useChartOps().chartHeight,
    loading: false,
    isEmpty: false,
    colors: () => useChartOps().colors,

    // 数据配置
    data: () => [0, 0, 0, 0, 0, 0, 0],
    xAxisData: () => [],
    lineWidth: useChartOps().lineWidth,
    lineOpacity: 1,
    showAreaColor: false,
    smooth: true,
    symbol: 'none',
    symbolSize: 6,
    animationDelay: 200,
    animationEnabled: true,
    yAxisMin: 0,
    yAxisName: '',
    valueUnit: '',
    showAllTooltipSeries: false,
    connectNulls: false,
    zeroIsEmpty: true,
    compactAxisLabels: false,
    xAxisLabelRotate: 0,
    showXAxisTick: false,
    xAxisInterval: 0,
    softenXAxis: false,
    showYAxisLine: true,
    showYAxisLabel: true,
    emphasizeAxis: false,
    emphasizeYAxisName: false,
    compactTooltip: false,
    thickenOnEmphasis: true,

    // 轴线显示配置
    showAxisLabel: true,
    showAxisLine: true,
    showSplitLine: true,

    // 交互配置
    showTooltip: true,
    showLegend: false,
    legendPosition: 'bottom'
  })

  // 动画状态管理
  const isAnimating = ref(false)
  const animationTimers = ref<number[]>([])
  const animatedData = ref<Array<number | null> | LineDataItem[]>([])

  // 清理所有定时器
  const clearAnimationTimers = () => {
    animationTimers.value.forEach((timer) => clearTimeout(timer))
    animationTimers.value = []
  }

  // 判断是否为多数据（使用 VueUse 的 computedEager 优化）
  const isMultipleData = computed(() => {
    return (
      Array.isArray(props.data) &&
      props.data.length > 0 &&
      props.data[0] !== null &&
      typeof props.data[0] === 'object' &&
      'name' in props.data[0]
    )
  })

  /**
   * 计算可空折线数据中的最大数值。
   * @param data 包含数值或 null 缺失点的折线数据。
   * @returns 数据中的最大数值，无有效值时返回 0。
   */
  const getDataMax = (data: Array<number | null>): number => {
    return data.reduce<number>((maximum, value) => {
      return value === null ? maximum : Math.max(maximum, value)
    }, 0)
  }

  // 缓存计算的最大值，避免重复计算
  const maxValue = computed(() => {
    if (isMultipleData.value) {
      const multiData = props.data as LineDataItem[]
      return multiData.reduce((max, item) => {
        if (item.data?.length) {
          const itemMax = getDataMax(item.data)
          return Math.max(max, itemMax)
        }
        return max
      }, 0)
    } else {
      const singleData = props.data as Array<number | null>
      return singleData?.length ? getDataMax(singleData) : 0
    }
  })

  // 初始化动画数据（优化：减少条件判断）
  const initAnimationData = (): Array<number | null> | LineDataItem[] => {
    if (isMultipleData.value) {
      const multiData = props.data as LineDataItem[]
      return multiData.map((item) => ({
        ...item,
        data: Array(item.data.length).fill(0)
      }))
    }
    const singleData = props.data as Array<number | null>
    return Array(singleData.length).fill(0)
  }

  // 复制真实数据（优化：使用结构化克隆）
  const copyRealData = (): Array<number | null> | LineDataItem[] => {
    if (isMultipleData.value) {
      return (props.data as LineDataItem[]).map((item) => ({ ...item, data: [...item.data] }))
    }
    return [...(props.data as Array<number | null>)]
  }

  // 获取颜色配置（优化：缓存主题色）
  const primaryColor = computed(() => getCssVar('--el-color-primary'))
  const axisLabelFontSize = computed(() =>
    props.compactAxisLabels ? useChartOps().smallFontSize : useChartOps().fontSize
  )
  const emphasizedAxisColor = computed(() => getCssVar('--art-gray-900'))
  const xAxisColor = computed(() =>
    getCssVar(props.softenXAxis ? '--art-gray-800' : '--art-gray-900')
  )
  const xAxisLabelColor = computed(() =>
    getCssVar(props.softenXAxis ? '--art-gray-700' : '--art-gray-900')
  )

  const getColor = (customColor?: string, index?: number): string => {
    if (customColor) return customColor
    if (index !== undefined) return props.colors![index % props.colors!.length]
    return primaryColor.value
  }

  // 生成区域样式
  const generateAreaStyle = (item: LineDataItem, color: string) => {
    // 如果有 areaStyle 配置，或者显式开启了区域颜色，则显示区域样式
    if (!item.areaStyle && !item.showAreaColor && !props.showAreaColor) return undefined

    const areaConfig = item.areaStyle || {}
    if (areaConfig.custom) return areaConfig.custom

    return {
      color: new graphic.LinearGradient(0, 0, 0, 1, [
        {
          offset: 0,
          color: hexToRgba(color, areaConfig.startOpacity || 0.2).rgba
        },
        {
          offset: 1,
          color: hexToRgba(color, areaConfig.endOpacity || 0.02).rgba
        }
      ])
    }
  }

  // 生成单数据区域样式
  const generateSingleAreaStyle = () => {
    if (!props.showAreaColor) return undefined

    const color = getColor(props.colors[0])
    return {
      color: new graphic.LinearGradient(0, 0, 0, 1, [
        {
          offset: 0,
          color: hexToRgba(color, 0.2).rgba
        },
        {
          offset: 1,
          color: hexToRgba(color, 0.02).rgba
        }
      ])
    }
  }

  /**
   * 创建 ECharts 折线系列配置。
   * @param config 系列数据和样式配置。
   * @returns ECharts 折线系列配置。
   */
  const createSeriesItem = (config: {
    name?: string
    data: Array<number | null>
    color?: string
    smooth?: boolean
    symbol?: string
    symbolSize?: number
    lineWidth?: number
    areaStyle?: any
  }) => {
    return {
      name: config.name,
      data: config.data,
      type: 'line' as const,
      connectNulls: props.connectNulls,
      color: config.color,
      smooth: config.smooth ?? props.smooth,
      symbol: config.symbol ?? props.symbol,
      symbolSize: config.symbolSize ?? props.symbolSize,
      lineStyle: {
        width: config.lineWidth ?? props.lineWidth,
        color: config.color,
        opacity: props.lineOpacity
      },
      areaStyle: config.areaStyle,
      emphasis: {
        focus: 'series' as const,
        lineStyle: {
          width: (config.lineWidth ?? props.lineWidth) + (props.thickenOnEmphasis ? 1 : 0)
        }
      }
    }
  }

  /**
   * 构建展示当前窗口全部系列的 tooltip。
   * @param parameters ECharts 当前坐标轴的系列参数。
   * @returns 可由 ECharts 安全渲染的 DOM 节点。
   */
  const formatAllSeriesTooltip = (parameters: any): HTMLElement => {
    const parameterList = Array.isArray(parameters) ? parameters : [parameters]
    const dataIndex = parameterList[0]?.dataIndex ?? 0
    const container = document.createElement('div')
    const axisLabel = document.createElement('div')
    axisLabel.textContent = props.xAxisData[dataIndex] ?? ''
    container.appendChild(axisLabel)

    if (isMultipleData.value) {
      const multiData = props.data as LineDataItem[]
      const markerParser = new DOMParser()
      multiData.forEach((item, index) => {
        const row = document.createElement('div')
        const value = item.data[dataIndex]
        const markerContent = echarts.format.getTooltipMarker({
          color: getColor(undefined, index),
          renderMode: 'html'
        })
        const markerDocument = markerParser.parseFromString(
          typeof markerContent === 'string' ? markerContent : '',
          'text/html'
        )
        const marker = markerDocument.body.firstElementChild
        if (marker) row.appendChild(document.importNode(marker, true))
        row.appendChild(
          document.createTextNode(
            `${item.name}: ${value === null || value === undefined ? '-' : `${value}${props.valueUnit}`}`
          )
        )
        container.appendChild(row)
      })
    }
    return container
  }

  /**
   * 生成当前折线图的 ECharts 配置。
   * @param isInitial 是否为动画初始化阶段。
   * @returns 包含坐标轴、tooltip、图例和数据系列的图表配置。
   */
  const generateChartOptions = (isInitial = false): EChartsOption => {
    const options: EChartsOption = {
      animation: props.animationEnabled,
      animationDuration: props.animationEnabled && !isInitial ? 1300 : 0,
      animationDurationUpdate: props.animationEnabled && !isInitial ? 1300 : 0,
      grid: getGridWithLegend(props.showLegend && isMultipleData.value, props.legendPosition, {
        top: 15,
        right: 15,
        left: 0
      }),
      tooltip: props.showTooltip
        ? getTooltipStyle('axis', {
            ...(props.showAllTooltipSeries ? { formatter: formatAllSeriesTooltip } : {}),
            ...(props.compactTooltip
              ? { textStyle: { fontSize: useChartOps().smallFontSize } }
              : {})
          })
        : undefined,
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: props.xAxisData,
        axisTick: {
          ...getAxisTickStyle(),
          show: props.showXAxisTick,
          interval: props.xAxisInterval,
          ...(props.emphasizeAxis ? { lineStyle: { color: xAxisColor.value } } : {})
        },
        axisLine: props.emphasizeAxis
          ? {
              show: props.showAxisLine,
              lineStyle: { color: xAxisColor.value }
            }
          : getAxisLineStyle(props.showAxisLine),
        axisLabel: {
          ...getAxisLabelStyle(props.showAxisLabel),
          ...(props.emphasizeAxis ? { color: xAxisLabelColor.value } : {}),
          fontSize: axisLabelFontSize.value,
          rotate: props.xAxisLabelRotate,
          interval: props.xAxisInterval,
          ...(props.xAxisLabelMargin !== undefined ? { margin: props.xAxisLabelMargin } : {})
        }
      },
      yAxis: {
        type: 'value',
        name: props.yAxisName,
        nameTextStyle: props.emphasizeYAxisName
          ? {
              color: props.emphasizeAxis ? emphasizedAxisColor.value : getCssVar('--art-gray-800')
            }
          : undefined,
        min: props.yAxisMin,
        max: props.yAxisMax ?? maxValue.value,
        axisLabel: {
          ...getAxisLabelStyle(props.showAxisLabel && props.showYAxisLabel),
          ...(props.emphasizeAxis ? { color: emphasizedAxisColor.value } : {}),
          fontSize: axisLabelFontSize.value,
          formatter: props.valueUnit ? `{value}${props.valueUnit}` : undefined
        },
        axisLine: props.emphasizeAxis
          ? {
              show: props.showYAxisLine,
              lineStyle: { color: emphasizedAxisColor.value }
            }
          : getAxisLineStyle(props.showYAxisLine),
        splitLine: getSplitLineStyle(props.showSplitLine)
      }
    }

    // 添加图例配置
    if (props.showLegend && isMultipleData.value) {
      options.legend = getLegendStyle(props.legendPosition)
    }

    // 生成系列数据
    if (isMultipleData.value) {
      const multiData = animatedData.value as LineDataItem[]
      options.series = multiData.map((item, index) => {
        const itemColor = getColor(props.colors[index], index)
        const areaStyle = generateAreaStyle(item, itemColor)

        return createSeriesItem({
          name: item.name,
          data: item.data,
          color: itemColor,
          smooth: item.smooth,
          symbol: item.symbol,
          lineWidth: item.lineWidth,
          areaStyle
        })
      })
    } else {
      // 单数据情况
      const singleData = animatedData.value as Array<number | null>
      const computedColor = getColor(props.colors[0])
      const areaStyle = generateSingleAreaStyle()

      options.series = [
        createSeriesItem({
          data: singleData,
          color: computedColor,
          areaStyle
        })
      ]
    }

    return options
  }

  // 更新图表
  const updateChartOptions = (options: EChartsOption) => {
    initChart(options)
  }

  // 初始化动画函数（优化：统一定时器管理，减少内存泄漏风险）
  const initChartWithAnimation = () => {
    clearAnimationTimers()
    isAnimating.value = true

    if (!props.animationEnabled) {
      animatedData.value = copyRealData()
      updateChartOptions(generateChartOptions(false))
      isAnimating.value = false
      return
    }

    // 初始化为0值数据
    animatedData.value = initAnimationData()
    updateChartOptions(generateChartOptions(true))

    if (isMultipleData.value) {
      // 多数据阶梯式动画
      const multiData = props.data as LineDataItem[]
      const currentAnimatedData = animatedData.value as LineDataItem[]

      multiData.forEach((item, index) => {
        const timer = window.setTimeout(
          () => {
            currentAnimatedData[index] = { ...item, data: [...item.data] }
            animatedData.value = [...currentAnimatedData]
            updateChartOptions(generateChartOptions(false))
          },
          index * props.animationDelay + 100
        )

        animationTimers.value.push(timer)
      })

      // 标记动画完成
      const totalDelay = (multiData.length - 1) * props.animationDelay + 1500
      const finishTimer = window.setTimeout(() => {
        isAnimating.value = false
      }, totalDelay)
      animationTimers.value.push(finishTimer)
    } else {
      // 单数据简单动画 - 使用 nextTick 确保初始状态已渲染
      nextTick(() => {
        animatedData.value = copyRealData()
        updateChartOptions(generateChartOptions(false))
        isAnimating.value = false
      })
    }
  }

  // 空数据检查函数
  const checkIsEmpty = () => {
    // 检查单数据情况
    if (!isMultipleData.value) {
      const singleData = props.data as Array<number | null>
      return (
        !singleData.length ||
        singleData.every((value) => value === null || (props.zeroIsEmpty && value === 0))
      )
    }

    // 检查多数据情况
    if (Array.isArray(props.data) && typeof props.data[0] === 'object') {
      const multiData = props.data as LineDataItem[]
      return (
        !multiData.length ||
        multiData.every(
          (item) =>
            !item.data?.length ||
            item.data.every((value) => value === null || (props.zeroIsEmpty && value === 0))
        )
      )
    }

    return true
  }

  // 使用新的图表组件抽象
  const {
    chartRef,
    initChart,
    getAxisLineStyle,
    getAxisLabelStyle,
    getAxisTickStyle,
    getSplitLineStyle,
    getTooltipStyle,
    getLegendStyle,
    getGridWithLegend,
    isEmpty
  } = useChartComponent({
    props,
    checkEmpty: checkIsEmpty,
    watchSources: [
      () => props.data,
      () => props.xAxisData,
      () => props.colors,
      () => props.lineOpacity,
      () => props.yAxisMax,
      () => props.valueUnit,
      () => props.compactAxisLabels,
      () => props.xAxisLabelRotate,
      () => props.xAxisLabelMargin,
      () => props.showXAxisTick,
      () => props.xAxisInterval,
      () => props.softenXAxis,
      () => props.showYAxisLine,
      () => props.showYAxisLabel,
      () => props.emphasizeAxis,
      () => props.emphasizeYAxisName,
      () => props.compactTooltip,
      () => props.thickenOnEmphasis
    ],
    onVisible: () => {
      // 当图表变为可见时，检查是否为空数据
      if (!isEmpty.value) {
        initChartWithAnimation()
      }
    },
    generateOptions: () => generateChartOptions(false)
  })

  // 图表渲染函数（优化：防止动画期间重复触发）
  const renderChart = () => {
    if (!isAnimating.value && !isEmpty.value) {
      initChartWithAnimation()
    }
  }

  // 使用 VueUse 的 watchDebounced 优化数据监听（避免频繁更新）
  watch(
    [
      () => props.data,
      () => props.xAxisData,
      () => props.colors,
      () => props.lineOpacity,
      () => props.yAxisMax,
      () => props.valueUnit,
      () => props.compactAxisLabels,
      () => props.xAxisLabelRotate,
      () => props.xAxisLabelMargin,
      () => props.showXAxisTick,
      () => props.xAxisInterval,
      () => props.softenXAxis,
      () => props.showYAxisLine,
      () => props.showYAxisLabel,
      () => props.emphasizeAxis,
      () => props.emphasizeYAxisName,
      () => props.compactTooltip,
      () => props.thickenOnEmphasis
    ],
    renderChart,
    { deep: true }
  )

  // 生命周期
  onMounted(() => {
    renderChart()
  })

  onBeforeUnmount(() => {
    clearAnimationTimers()
  })
</script>
