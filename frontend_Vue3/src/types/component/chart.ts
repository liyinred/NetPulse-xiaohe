/**
 * 图表组件类型定义模块
 *
 * 提供 ECharts 图表组件的完整类型定义
 *
 * ## 主要功能
 *
 * - 基础图表配置类型
 * - 柱状图类型定义
 * - 折线图类型定义
 * - 饼图/环形图类型定义
 * - 雷达图类型定义
 * - K线图类型定义
 * - 散点图类型定义
 * - 地图图表类型定义
 * - 双向堆叠柱状图类型定义
 * - 图表主题配置类型
 * - 图表事件回调类型
 *
 * ## 使用场景
 *
 * - 图表组件 Props 类型约束
 * - 图表配置类型定义
 * - 图表数据结构定义
 * - 图表事件处理
 *
 * @module types/component/chart
 * @author Art Design Pro Team
 */
import type { EChartsOption } from '@/plugins/echarts'

// 图例位置类型
export type LegendPosition = 'bottom' | 'top' | 'left' | 'right'

export type SymbolType =
  | 'circle'
  | 'rect'
  | 'roundRect'
  | 'triangle'
  | 'diamond'
  | 'pin'
  | 'arrow'
  | 'none'

// 图表主题配置
export interface ChartThemeConfig {
  /** 图表高度 */
  chartHeight: string
  /** 字体大小 */
  fontSize: number
  /** 紧凑字体大小 */
  smallFontSize: number
  /** 极小字体大小 */
  tinyFontSize: number
  /** 默认折线宽度 */
  lineWidth: number
  /** 细折线宽度 */
  thinLineWidth: number
  /** 字体颜色 */
  fontColor: string
  /** 主题颜色 */
  themeColor: string
  /** 颜色组 */
  colors: string[]
}

// 图表初始化选项
export interface UseChartOptions {
  /** 初始化选项 */
  initOptions?: EChartsOption
  /** 延迟初始化时间(ms) */
  initDelay?: number
  /** IntersectionObserver阈值 */
  threshold?: number
  /** 是否自动响应主题变化 */
  autoTheme?: boolean
}

// 基础图表 Props 接口 - 统一所有图表的基础属性
export interface BaseChartProps {
  /** 图表高度 */
  height?: string
  /** 是否加载中 */
  loading?: boolean
  isEmpty?: boolean
  /** 颜色配置 */
  colors?: string[]
}

// 轴线显示控制接口 - 统一轴线相关配置
export interface AxisDisplayProps {
  /** 是否显示坐标轴标签 */
  showAxisLabel?: boolean
  /** 是否显示坐标轴线 */
  showAxisLine?: boolean
  /** 是否显示分割线 */
  showSplitLine?: boolean
}

// 交互显示控制接口 - 统一交互相关配置
export interface InteractionProps {
  /** 是否显示提示框 */
  showTooltip?: boolean
  /** 是否显示图例 */
  showLegend?: boolean
  /** 图例位置 */
  legendPosition?: LegendPosition
}

// 柱状图数据项接口
export interface BarDataItem {
  /** 系列名称 */
  name: string
  /** 数据值 */
  data: number[]
  /** 柱状图宽度 */
  barWidth?: string | number
  /** 堆叠分组名称 */
  stack?: string
}

// 柱状图 Props 接口 - 统一柱状图配置
export interface BarChartProps extends BaseChartProps, AxisDisplayProps, InteractionProps {
  /** 图表数据 - 支持单组数据或多组数据 */
  data: number[] | BarDataItem[]
  /** X轴标签数据 */
  xAxisData?: string[]
  /** 柱状图宽度 */
  barWidth?: string | number
  /** 是否堆叠显示 */
  stack?: boolean
  /** 圆角 */
  borderRadius?: number | number[]
}

// 折线图数据项接口
export interface LineDataItem {
  /** 系列名称 */
  name: string
  /** 数据值，null 表示当前横轴窗口无记录 */
  data: Array<number | null>
  /** 线条宽度 */
  lineWidth?: number
  /** 是否显示区域填充 */
  showAreaColor?: boolean
  /** 区域样式配置 */
  areaStyle?: {
    /** 渐变开始透明度 */
    startOpacity?: number
    /** 渐变结束透明度 */
    endOpacity?: number
    /** 自定义 ECharts areaStyle 配置 */
    custom?: any
  }
  /** 是否平滑曲线 */
  smooth?: boolean
  /** 数据点符号 */
  symbol?: SymbolType
  /** 数据点大小 */
  symbolSize?: number
}

// 折线图 Props 接口 - 统一折线图配置
export interface LineChartProps extends BaseChartProps, AxisDisplayProps, InteractionProps {
  /** 图表数据 - 支持单组数据或多组数据 */
  data: Array<number | null> | LineDataItem[]
  /** X轴标签数据 */
  xAxisData?: string[]
  /** 线条宽度 */
  lineWidth?: number
  /** 曲线透明度 */
  lineOpacity?: number
  /** 是否显示区域填充 */
  showAreaColor?: boolean
  /** 是否平滑曲线 */
  smooth?: boolean
  /** 数据点符号 */
  symbol?: SymbolType
  /** 数据点大小 */
  symbolSize?: number
  /** 多数据动画延迟间隔（毫秒） */
  animationDelay?: number
  /** 是否启用阶梯式动画 */
  animationEnabled?: boolean
  /** Y轴最小值 */
  yAxisMin?: number
  /** Y轴最大值，不传时根据数据计算 */
  yAxisMax?: number
  /** Y轴名称 */
  yAxisName?: string
  /** 数值展示单位 */
  valueUnit?: string
  /** tooltip 是否展示当前窗口的全部系列 */
  showAllTooltipSeries?: boolean
  /** tooltip 中需要标红的指标值 */
  tooltipAlertValue?: number
  /** 是否连接 null 缺失点 */
  connectNulls?: boolean
  /** 是否将全零序列视为空数据 */
  zeroIsEmpty?: boolean
  /** 是否使用紧凑坐标轴刻度字号 */
  compactAxisLabels?: boolean
  /** X轴刻度旋转角度 */
  xAxisLabelRotate?: number
  /** X轴刻度线与刻度值的间距 */
  xAxisLabelMargin?: number
  /** 是否显示X轴刻度线 */
  showXAxisTick?: boolean
  /** X轴刻度与标签间隔，0 表示全部显示 */
  xAxisInterval?: number
  /** 是否将X轴线、刻度和刻度值调整为较浅灰阶 */
  softenXAxis?: boolean
  /** 是否显示Y轴轴线 */
  showYAxisLine?: boolean
  /** 是否显示Y轴刻度值 */
  showYAxisLabel?: boolean
  /** 是否使用深色坐标轴线、刻度和标签 */
  emphasizeAxis?: boolean
  /** 是否强调Y轴标题 */
  emphasizeYAxisName?: boolean
  /** 是否使用紧凑 tooltip 字号 */
  compactTooltip?: boolean
  /** tooltip 自定义字号 */
  tooltipFontSize?: number
  /** emphasis 状态下是否加粗曲线 */
  thickenOnEmphasis?: boolean
  /** 是否使用 ECharts 内置颜色组 */
  useBuiltInPalette?: boolean
  /** 图例所在方向为绘图区预留的空间 */
  legendSpace?: number
  /** 图例文字自定义字号 */
  legendFontSize?: number
  /** 鼠标悬停图例时是否高亮关联曲线 */
  legendHoverLink?: boolean
  /** 是否允许 Shift + 鼠标左键独占显示图例对应曲线 */
  shiftLegendExclusiveSelect?: boolean
}

// 雷达图数据项接口
export interface RadarDataItem {
  /** 系列名称 */
  name: string
  /** 数据值 */
  value: number[]
}

// 雷达图 Props 接口 - 统一雷达图配置
export interface RadarChartProps extends BaseChartProps, InteractionProps {
  /** 雷达图指标配置 */
  indicator?: Array<{ name: string; max: number }>
  /** 图表数据 */
  data?: RadarDataItem[]
}

// 饼图/环形图数据项接口
export interface PieDataItem {
  /** 数据值 */
  value: number
  /** 数据名称 */
  name: string
}

// 环形图 Props 接口 - 统一环形图配置
export interface RingChartProps extends BaseChartProps, InteractionProps {
  /** 图表数据 */
  data: PieDataItem[]
  /** 内外半径 */
  radius?: string[]
  /** 边框圆角 */
  borderRadius?: number
  /** 中心文本 */
  centerText?: string
  /** 是否显示标签 */
  showLabel?: boolean
}

// K线图数据项接口
export interface KLineDataItem {
  /** 时间标签 */
  time: string
  /** 开盘价 */
  open: number
  /** 收盘价 */
  close: number
  /** 最高价 */
  high: number
  /** 最低价 */
  low: number
}

// K线图 Props 接口 - 统一K线图配置
export interface KLineChartProps extends BaseChartProps {
  /** 图表数据 */
  data?: KLineDataItem[]
  /** 是否显示数据缩放控件 */
  showDataZoom?: boolean
  /** 数据缩放初始开始位置 */
  dataZoomStart?: number
  /** 数据缩放初始结束位置 */
  dataZoomEnd?: number
}

// 散点图数据项接口
export interface ScatterDataItem {
  /** 坐标值 [x, y] */
  value: number[]
}

// 散点图 Props 接口 - 统一散点图配置
export interface ScatterChartProps extends BaseChartProps, AxisDisplayProps, InteractionProps {
  /** 图表数据 */
  data?: ScatterDataItem[]
  /** 散点大小 */
  symbolSize?: number
}

// 双柱对比图 Props 接口 - 统一双柱对比图配置
export interface DualBarCompareChartProps extends BaseChartProps {
  /** 上方数据 */
  topData: number[]
  /** 下方数据 */
  bottomData: number[]
  /** X轴标签数据 */
  xAxisData: string[]
  /** 上方柱子颜色 */
  topColor?: string
  /** 下方柱子颜色 */
  bottomColor?: string
  /** 柱状图宽度 */
  barWidth?: number
}

// 地图图表 Props 接口 - 统一地图图表配置
export interface MapChartProps extends BaseChartProps {
  /** 地图数据 */
  mapData?: any[]
  /** 选中区域 */
  selectedRegion?: string
  /** 是否显示标签 */
  showLabels?: boolean
  /** 是否显示散点 */
  showScatter?: boolean
}

// 双向堆叠柱状图 Props 接口（人口金字塔样式）
export interface BidirectionalBarChartProps
  extends BaseChartProps,
    AxisDisplayProps,
    InteractionProps {
  /** 正向数据（向上显示） */
  positiveData: number[]
  /** 负向数据（向下显示） */
  negativeData: number[]
  /** X轴标签数据 */
  xAxisData?: string[]
  /** 正向数据名称 */
  positiveName?: string
  /** 负向数据名称 */
  negativeName?: string
  /** 柱状图宽度 */
  barWidth?: string | number
  /** Y轴最小值 */
  yAxisMin?: number
  /** Y轴最大值 */
  yAxisMax?: number
  /** 是否显示数据标签 */
  showDataLabel?: boolean
  /** 正向数据圆角配置 */
  positiveBorderRadius?: number | number[]
  /** 负向数据圆角配置 */
  negativeBorderRadius?: number | number[]
}

// 图表配置生成器函数类型
export type ChartOptionGenerator = () => EChartsOption

// 图表事件回调类型
export type ChartEventCallback = (params: any) => void

// 图表错误信息接口
export interface ChartError {
  /** 错误码 */
  code: string
  /** 错误信息 */
  message: string
  /** 错误详情 */
  details?: any
}
